#!/bin/bash

cd .. && docker build --no-cache -t firmcorr-angr -f Dockerfile.angr .
