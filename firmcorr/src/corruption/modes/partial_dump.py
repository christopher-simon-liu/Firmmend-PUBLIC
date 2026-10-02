"""Partial dump corruption mode."""

from collections.abc import Callable
from random import Random


def apply_partial_dump(
	data: bytearray,
	target_bytes: int,
	affected_mask: bytearray,
	*,
	firmware_start: int,
	firmware_end: int,
	rng: Random,
	clamp_boundary: Callable[[int, int, int], int | None],
) -> tuple[bytearray, int, int]:
	"""Apply partial dump corruption by truncating the output."""
	size = len(data)
	firmware_size = firmware_end - firmware_start
	target_bytes = max(0, min(firmware_size, int(target_bytes)))

	if target_bytes == 0:
		return data, 0, size

	truncate_at = firmware_end - target_bytes
	jitter = int(target_bytes * 0.1 * (rng.random() * 2 - 1))
	truncate_at = clamp_boundary(truncate_at + jitter, firmware_start, firmware_end)
	if truncate_at is None:
		return data, 0, size

	corrupted = size - truncate_at
	for i in range(truncate_at, size):
		affected_mask[i] = 1
	del data[truncate_at:]

	return data, corrupted, truncate_at
