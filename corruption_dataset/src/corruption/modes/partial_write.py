"""Partial write corruption mode."""

from collections.abc import Callable
from random import Random


def apply_partial_write(
	data: bytearray,
	target_bytes: int,
	affected_mask: bytearray,
	*,
	firmware_start: int,
	firmware_end: int,
	rng: Random,
	clamp_boundary: Callable[[int, int, int], int | None],
) -> tuple[bytearray, int]:
	"""Apply partial write corruption by leaving the tail unwritten."""
	region_size = firmware_end - firmware_start
	target_bytes = max(0, min(region_size, int(target_bytes)))

	if target_bytes == 0:
		return data, 0

	write_end = firmware_end - target_bytes
	jitter = int(target_bytes * 0.1 * (rng.random() * 2 - 1))
	write_end = clamp_boundary(write_end + jitter, firmware_start, firmware_end)
	if write_end is None:
		return data, 0

	corrupted = 0
	for i in range(write_end, firmware_end):
		data[i] = 0xFF
		affected_mask[i] = 1
		corrupted += 1

	return data, corrupted
