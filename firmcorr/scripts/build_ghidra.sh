#!/bin/bash

cd .. && docker build --no-cache -t firmcorr-ghidra -f Dockerfile.ghidra .
