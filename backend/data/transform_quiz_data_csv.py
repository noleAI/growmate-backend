import csv
import json
import os
import argparse
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_NDJSON = os.path.join(BASE_DIR, 'quiz_question_template_normalized.ndjson')
OUTPUT_CSV = os.path.join(BASE_DIR, 'quiz_question_template.csv')

# Keep the same logical columns expected by DB import mapping.
OUTPUT_COLUMNS = [
	'subject',
	'topic_code',
	'topic_name',
	'exam_year',
	'question_type',
	'part_no',
	'difficulty_level',
	'content',
	'media_url',
	'payload',
	'metadata',
	'is_active',
	'grade_level',
]

VALID_QUESTION_TYPES = {'MULTIPLE_CHOICE', 'TRUE_FALSE_CLUSTER', 'SHORT_ANSWER'}


def _as_json_object_text(value, default_obj):
	"""
	Convert value to a valid JSON text for jsonb columns.
	Ensures payload/metadata are serialized as JSON objects.
	"""
	if value is None:
		return json.dumps(default_obj, ensure_ascii=False)

	if isinstance(value, dict):
		return json.dumps(value, ensure_ascii=False)

	if isinstance(value, str):
		stripped = value.strip()
		if not stripped:
			return json.dumps(default_obj, ensure_ascii=False)
		try:
			parsed = json.loads(stripped)
		except json.JSONDecodeError:
			return json.dumps(default_obj, ensure_ascii=False)
		if isinstance(parsed, dict):
			return json.dumps(parsed, ensure_ascii=False)
		return json.dumps(default_obj, ensure_ascii=False)

	return json.dumps(default_obj, ensure_ascii=False)


def _as_bool_text(value, default=True):
	if value is None:
		return 'true' if default else 'false'

	if isinstance(value, bool):
		return 'true' if value else 'false'

	if isinstance(value, str):
		normalized = value.strip().lower()
		if normalized in {'true', 't', '1', 'yes', 'y'}:
			return 'true'
		if normalized in {'false', 'f', '0', 'no', 'n'}:
			return 'false'
		return 'true' if default else 'false'

	return 'true' if bool(value) else 'false'


def _safe_int(value, default):
	try:
		return int(str(value).strip())
	except (TypeError, ValueError):
		return default


def _normalize_question_type(value):
	text = (value or '').strip().upper()
	if text in VALID_QUESTION_TYPES:
		return text
	return 'MULTIPLE_CHOICE'


def _normalize_part_no(value, question_type):
	part_no = _safe_int(value, 0)
	if part_no in {1, 2, 3}:
		return part_no

	if question_type == 'MULTIPLE_CHOICE':
		return 1
	if question_type == 'TRUE_FALSE_CLUSTER':
		return 2
	return 3


def _normalize_content(value):
	text = (value or '').strip()
	if text:
		return text
	return 'No content provided'


def _normalize_difficulty(value):
	difficulty = _safe_int(value, 2)
	if difficulty < 1:
		return 1
	if difficulty > 5:
		return 5
	return difficulty


def _write_csv_rows(rows, output_csv):
	# Try to clear read-only bit before writing (common on Windows).
	if os.path.exists(output_csv):
		try:
			os.chmod(output_csv, 0o666)
		except OSError:
			pass

	with open(output_csv, 'w', encoding='utf-8', newline='') as outfile:
		writer = csv.DictWriter(outfile, fieldnames=OUTPUT_COLUMNS, quoting=csv.QUOTE_MINIMAL)
		writer.writeheader()
		writer.writerows(rows)


def _fallback_output_path(output_csv):
	base, ext = os.path.splitext(output_csv)
	if not ext:
		ext = '.csv'
	stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
	return f'{base}_{stamp}{ext}'


def convert_ndjson_to_csv(input_ndjson=INPUT_NDJSON, output_csv=OUTPUT_CSV, strict=False):
	rows = []
	skipped = 0

	with open(input_ndjson, 'r', encoding='utf-8') as infile:
		for line_number, line in enumerate(infile, start=1):
			line = line.strip()
			if not line:
				continue

			try:
				obj = json.loads(line)
			except json.JSONDecodeError as exc:
				if strict:
					raise ValueError(f'Invalid NDJSON at line {line_number}: {exc}') from exc
				skipped += 1
				continue

			question_type = _normalize_question_type(obj.get('question_type'))
			part_no = _normalize_part_no(obj.get('part_no'), question_type)
			payload_json = _as_json_object_text(obj.get('payload'), {})
			metadata_json = _as_json_object_text(obj.get('metadata'), {})

			row = {
				'subject': obj.get('subject', 'math'),
				'topic_code': obj.get('topic_code'),
				'topic_name': obj.get('topic_name'),
				'exam_year': _safe_int(obj.get('exam_year'), 2026),
				'question_type': question_type,
				'part_no': part_no,
				'difficulty_level': _normalize_difficulty(obj.get('difficulty_level', 2)),
				'content': _normalize_content(obj.get('content')),
				'media_url': obj.get('media_url') or '',
				'payload': payload_json,
				'metadata': metadata_json,
				'is_active': _as_bool_text(obj.get('is_active', True), default=True),
				'grade_level': str(obj.get('grade_level') or '11'),
			}
			rows.append(row)

	final_output_csv = output_csv
	try:
		_write_csv_rows(rows, output_csv)
	except PermissionError:
		final_output_csv = _fallback_output_path(output_csv)
		_write_csv_rows(rows, final_output_csv)
		print(
			f'Canh bao: Khong the ghi vao {output_csv}. '
			f'File co the dang mo/bi khoa. Da ghi sang {final_output_csv}.'
		)

	return len(rows), final_output_csv, skipped


def parse_args():
	parser = argparse.ArgumentParser(
		description='Convert quiz_question_template NDJSON to CSV for Supabase import.'
	)
	parser.add_argument('--input', default=INPUT_NDJSON, help='Path to NDJSON input file')
	parser.add_argument('--output', default=OUTPUT_CSV, help='Path to CSV output file')
	parser.add_argument(
		'--strict',
		action='store_true',
		help='Stop on invalid NDJSON line instead of skipping it',
	)
	return parser.parse_args()


if __name__ == '__main__':
	args = parse_args()
	count, out_path, skipped = convert_ndjson_to_csv(
		input_ndjson=args.input,
		output_csv=args.output,
		strict=args.strict,
	)
	print(f'Chuyen doi thanh cong {count} dong vao {out_path}. Bo qua {skipped} dong loi.')