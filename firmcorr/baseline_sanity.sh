#!/usr/bin/env bash

echo "Running baseline sanity checks..."

echo "Same baseline binary, different runs"
./scripts/run_fuzzware.sh dataset/corruption/CNC/address_bit_freeze_0.0_baseline/CNC.address_bit_freeze-0.0.bin  results/same 00:00:1:00 1
./scripts/run_fuzzware.sh dataset/corruption/CNC/bit_flip_0.0_baseline/CNC.bit_flip-0.0.bin results/same 00:00:1:00 1
./scripts/run_fuzzware.sh dataset/corruption/CNC/partial_dump_0.0_baseline/CNC.partial_dump-0.0.bin results/same 00:00:1:00 1
./scripts/run_fuzzware.sh dataset/corruption/CNC/partial_write_0.0_baseline/CNC.partial_write-0.0.bin results/same 00:00:1:00 1
./scripts/run_fuzzware.sh dataset/corruption/CNC/partial_erase_0.0_baseline/CNC.partial_erase-0.0.bin results/same 00:00:1:00 1

echo "All binaries once"
./scripts/run_fuzzware.sh dataset/corruption/CNC/bit_flip_0.0_baseline/CNC.bit_flip-0.0.bin results/diff 00:00:1:00 1
./scripts/run_fuzzware.sh dataset/corruption/Console/bit_flip_0.0_baseline/Console.bit_flip-0.0.bin results/diff 00:00:1:00 1
./scripts/run_fuzzware.sh dataset/corruption/Drone/bit_flip_0.0_baseline/Drone.bit_flip-0.0.bin results/diff 00:00:1:00 1
./scripts/run_fuzzware.sh dataset/corruption/Gateway/bit_flip_0.0_baseline/Gateway.bit_flip-0.0.bin results/diff 00:00:1:00 1
./scripts/run_fuzzware.sh dataset/corruption/Heat_Press/bit_flip_0.0_baseline/Heat_Press.bit_flip-0.0.bin results/diff 00:00:1:00 1
./scripts/run_fuzzware.sh dataset/corruption/PLC/bit_flip_0.0_baseline/PLC.bit_flip-0.0.bin results/diff 00:00:1:00 1
./scripts/run_fuzzware.sh dataset/corruption/Reflow_Oven/bit_flip_0.0_baseline/Reflow_Oven.bit_flip-0.0.bin results/diff 00:00:1:00 1
./scripts/run_fuzzware.sh dataset/corruption/Soldering_Iron/bit_flip_0.0_baseline/Soldering_Iron.bit_flip-0.0.bin results/diff 00:00:1:00 1
./scripts/run_fuzzware.sh dataset/corruption/Steering_Control/bit_flip_0.0_baseline/Steering_Control.bit_flip-0.0.bin results/diff 00:00:1:00 1

