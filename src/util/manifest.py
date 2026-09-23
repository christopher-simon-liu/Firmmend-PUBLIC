import argparse
import hashlib
import json
import logging
import os
from pathlib import Path


logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]


def parse_arguments():
	parser = argparse.ArgumentParser(
		prog=os.path.basename(__file__),
		description="Generate a RepairCandidate manifest for a mended binary",
	)
	parser.add_argument("mended_binary", help="Path to the mended binary")
	parser.add_argument("corrupted_binary", help="Path to the corrupted binary")
	parser.add_argument("original_binary", help="Path to the ideal original binary")
	parser.add_argument("output_folder", help="Path to output folder")
	parser.add_argument(
		"--method",
		default=None,
		help="Repair method name (default: parsed from the mended binary name)",
	)
	parser.add_argument(
		"--mask-id",
		default=None,
		help="Corruption mask identifier (default: mended binary name without .mend.bin)",
	)
	parser.add_argument(
		"--parameter",
		action="append",
		default=[],
		metavar="KEY=VALUE",
		help="Extra method parameter recorded alongside the binary paths; may be repeated",
	)
	return parser.parse_args()


def _sha256(data: bytes) -> str:
	return hashlib.sha256(data).hexdigest()


def _byte_at(data: bytes, offset: int) -> int:
	return data[offset] if offset < len(data) else -1


def _repo_relative(path: Path) -> str:
	resolved = path.resolve()
	try:
		return resolved.relative_to(REPO_ROOT).as_posix()
	except ValueError:
		return resolved.as_posix()


def _parse_parameters(pairs):
	parameters = {}
	for pair in pairs:
		key, separator, value = pair.partition("=")
		if not separator or not key:
			raise ValueError(f"Parameter must be KEY=VALUE: {pair!r}")
		parameters[key] = value
	return parameters


def _stem_from_name(mend_name: str) -> str:
	"""Mended binaries are named <stem>.<method>.mend.bin."""
	stem = mend_name
	for suffix in (".bin", ".mend"):
		if stem.endswith(suffix):
			stem = stem[: -len(suffix)]
	return stem


def _method_from_name(mend_name: str) -> str:
	_, _, method = _stem_from_name(mend_name).rpartition(".")
	return method or "unknown"


def build_manifest(
	mended: bytes,
	corrupted: bytes,
	original: bytes,
	method_name: str,
	parameters: dict,
	mask_id: str,
):
	corrupted_offsets = [
		offset
		for offset in range(max(len(mended), len(corrupted), len(original)))
		if _byte_at(corrupted, offset) != _byte_at(original, offset)
	]
	total_corrupted_bytes = len(corrupted_offsets)
	matching_mend_bytes = sum(
		_byte_at(mended, offset) == _byte_at(original, offset)
		for offset in corrupted_offsets
	)
	edits = [
		{
			"offset": offset,
			"original_byte": _byte_at(original, offset),
			"corrupted_byte": _byte_at(corrupted, offset),
			"mend_bytes": [_byte_at(mended, offset)],
		}
		for offset in range(max(len(mended), len(corrupted)))
		if _byte_at(mended, offset) != _byte_at(corrupted, offset)
	]

	return {
		"input_sha256": _sha256(corrupted),
		"mask_id": mask_id,
		"method_name": method_name,
		"parameters": parameters,
		"edits": edits,
		"repair_correctness": {
			"total_corrupted_bytes": total_corrupted_bytes,
			"matching_mend_bytes": matching_mend_bytes,
			"repair_correctness_ratio": (
				matching_mend_bytes / total_corrupted_bytes
				if total_corrupted_bytes
				else None
			),
		},
		"output_sha256": _sha256(mended),
	}


def main():
	args = parse_arguments()
	mended_path = Path(args.mended_binary)
	corrupted_path = Path(args.corrupted_binary)
	original_path = Path(args.original_binary)
	output_folder = Path(args.output_folder)

	manifest = build_manifest(
		mended_path.read_bytes(),
		corrupted_path.read_bytes(),
		original_path.read_bytes(),
		args.method or _method_from_name(mended_path.name),
		{
			"mended_binary": _repo_relative(mended_path),
			"corrupted_binary": _repo_relative(corrupted_path),
			"original_binary": _repo_relative(original_path),
			**_parse_parameters(args.parameter),
		},
		args.mask_id or _stem_from_name(mended_path.name),
	)

	output_folder.mkdir(parents=True, exist_ok=True)
	out_path = output_folder / "manifest.json"
	logger.info("Creating %s", out_path)
	out_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
	main()
