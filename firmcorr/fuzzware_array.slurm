#!/bin/bash
# fuzzware_array.slurm — 500x 24hr fuzzware campaigns via SLURM array job
#
# BEFORE SUBMITTING:
#   1. Run generate_targets.sh to discover all config.yml targets and write targets.txt:
#        bash generate_targets.sh /work/liuc1/firmcorr/dataset/corruption
#   2. Update --array=1-N below to match the count printed by generate_targets.sh
#   3. Adjust --cpus-per-task and --mem if needed
#   4. mkdir -p logs results
#=============================================================================

#SBATCH --job-name=fuzzware
#SBATCH --array=1-500%450         # N = line count of targets.txt; set before submitting
#SBATCH --time=24:00:00           # 24hr wall time per run
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4         # cores per fuzzer — adjust as needed
#SBATCH --mem=32G                 # angr (modeling worker) is memory-intensive; 4G causes OOM crashes
#SBATCH --output=/work/liuc1/firmcorr/logs/fuzz_%A_%a.out
#SBATCH --error=/work/liuc1/firmcorr/logs/fuzz_%A_%a.err
#SBATCH --partition=CPU     

# -----------------------------------------------------------------------------
# USER CONFIGURATION — edit these
# -----------------------------------------------------------------------------
REPO_DIR=/work/liuc1/firmcorr         # Path to your uploaded firmcorr repo
IMAGE_PATH=/apps/containers/firmcorr.sif
OUTPUT_DIR=${REPO_DIR}/results/run_${SLURM_ARRAY_TASK_ID}

TARGETS_LIST=${REPO_DIR}/targets.txt
TARGET_DIR=$(sed -n "${SLURM_ARRAY_TASK_ID}p" "${TARGETS_LIST}")

if [ -z "${TARGET_DIR}" ]; then
  echo "Error: no target found for task ID ${SLURM_ARRAY_TASK_ID} in ${TARGETS_LIST}" >&2
  exit 1
fi

# Extract firmware family name (top-level subdir under dataset/corruption)
FW_NAME=$(echo "${TARGET_DIR}" | sed -E 's|dataset/corruption/([^/]+)/.*|\1|')

# Resolve binary: check config dir first, then dataset/original/<fw>/
CONFIG_DIR="${REPO_DIR}/${TARGET_DIR}"
BIN_NAME=$(grep -E '^[[:space:]]*file:[[:space:]]' "${CONFIG_DIR}/config.yml" \
  | head -n1 | sed -E 's/^[[:space:]]*file:[[:space:]]*//; s/[[:space:]]*//')

if [ -f "${CONFIG_DIR}/${BIN_NAME}" ]; then
  BIN_PATH="${CONFIG_DIR}/${BIN_NAME}"
elif [ -f "${REPO_DIR}/dataset/original/${FW_NAME}/${BIN_NAME}" ]; then
  BIN_PATH="${REPO_DIR}/dataset/original/${FW_NAME}/${BIN_NAME}"
else
  echo "Error: binary '${BIN_NAME}' not found for ${TARGET_DIR}" >&2
  exit 1
fi

set -euo pipefail

echo "[$(date)] Starting fuzz run ${SLURM_ARRAY_TASK_ID} on $(hostname)"
echo "CPUs: ${SLURM_CPUS_PER_TASK}  MEM: ${SLURM_MEM_PER_NODE}MB"

mkdir -p "${OUTPUT_DIR}"

# Skip rerun if a completed summary already exists for this task output.
# Summary filenames are typically like <firmware>.bin_fuzzware.json.
if compgen -G "${OUTPUT_DIR}/*_fuzzware.json" > /dev/null; then
  EXISTING_SUMMARY="$(find "${OUTPUT_DIR}" -maxdepth 1 -type f -name '*_fuzzware.json' | head -n1)"
  echo "[$(date)] Skipping run ${SLURM_ARRAY_TASK_ID}: found ${EXISTING_SUMMARY}"
  exit 0
fi

# Stage config dir + binary into OUTPUT_DIR/target/ (writable by job owner).
# fuzzware_entrypoint_hpc.sh copies this to /output/workdir/ inside the container,
# so the read-only dataset is never touched and the binary path is always resolved.
STAGE_DIR="${OUTPUT_DIR}/target"
mkdir -p "${STAGE_DIR}"
cp -r "${CONFIG_DIR}/." "${STAGE_DIR}/"
if [ ! -f "${STAGE_DIR}/${BIN_NAME}" ]; then
  cp "${BIN_PATH}" "${STAGE_DIR}/${BIN_NAME}"
fi

# fuzzware-project lands at OUTPUT_DIR/workdir/fuzzware-project/ (persisted, not cleaned up)
PROJECT_DIR="${OUTPUT_DIR}/workdir/fuzzware-project"

set +e
singularity exec \
  --no-home \
  --bind "${REPO_DIR}:/firmcorr" \
  --bind "${OUTPUT_DIR}:/output" \
  --bind "/work/liuc1/firmcorr/pool.py:/home/user/fuzzware/pipeline/fuzzware_pipeline/workers/pool.py:ro" \
  --bind "/work/liuc1/firmcorr/rq_worker.py:/home/user/.virtualenvs/fuzzware-modeling/lib/python3.10/site-packages/fuzzware_modeling/rq_worker.py:ro" \
  --bind "/work/liuc1/firmcorr/fuzzware_entrypoint_hpc.sh:/home/user/fuzzware_entrypoint_hpc.sh:ro" \
  --bind "/work/liuc1/firmcorr/src/measurement/dynamic/fuzzware_summary.py:/home/user/fuzzware_summary.py:ro" \
  --env AFL_I_DONT_CARE_ABOUT_MISSING_CRASHES=1 \
  --env AFL_NO_AFFINITY=1 \
  --env PYTHON_EGG_CACHE=/tmp/pyeggs \
  --env FUZZWARE_RUN_FOR="01:00:00:00" \
  --env FUZZWARE_NUM_FUZZERS=1 \
  "${IMAGE_PATH}" \
  bash /home/user/fuzzware_entrypoint_hpc.sh \
    "/output/target/${BIN_NAME}" \
    "/output"
EXIT_CODE=$?
set -e

echo "[$(date)] Run ${SLURM_ARRAY_TASK_ID} finished with exit code ${EXIT_CODE}"

# -----------------------------------------------------------------------------
# FAILURE DIAGNOSTICS
# On any non-zero exit, gather the evidence needed to distinguish an OOM-kill of the
# memory-hungry "modeling" worker from an in-process angr/Redis fault. Everything here is
# best-effort and must never itself fail the job.
# -----------------------------------------------------------------------------
if [ "${EXIT_CODE}" -ne 0 ]; then
  ACCT_ID="${SLURM_ARRAY_JOB_ID}_${SLURM_ARRAY_TASK_ID}"
  echo "===================== FAILURE DIAGNOSTICS (${ACCT_ID}) ====================="

  # 1. SLURM resource accounting — State=OUT_OF_MEMORY, ExitCode signalling 9, or MaxRSS
  #    approaching the requested --mem all point to an OOM-kill inside the job cgroup.
  if command -v sacct >/dev/null 2>&1; then
    echo "--- sacct ---"
    sacct -j "${ACCT_ID}" \
      --format=JobID,JobName%18,State,ExitCode,DerivedExitCode,MaxRSS,MaxVMSize,ReqMem,NodeList%18 \
      2>/dev/null || echo "(sacct query failed)"
  fi
  if command -v seff >/dev/null 2>&1; then
    echo "--- seff ---"
    seff "${ACCT_ID}" 2>/dev/null || echo "(seff query failed)"
  fi

  # 2. Kernel OOM-killer messages from the compute node (usually needs privileges; harmless
  #    if denied). A "Killed process … (python3|redis-server)" line is the definitive OOM proof.
  echo "--- dmesg OOM scan ---"
  (dmesg -T 2>/dev/null | grep -iE 'killed process|out of memory|oom-kill' | tail -20) \
    || echo "(dmesg not accessible on this node)"

  # 3. Fuzzware's per-worker logs. The "modeling" worker is the angr/state-generation process;
  #    a clean SIGKILL with no Python traceback => OOM-killed externally, whereas a MemoryError
  #    or angr stack trace => the worker blew up in-process (still memory, but caught by Python).
  echo "--- fuzzware worker logs (tail) ---"
  if [ -d "${PROJECT_DIR}" ]; then
    find "${PROJECT_DIR}" -path '*logs*' -type f 2>/dev/null \
      | grep -iE 'modeling|worker|pipeline' \
      | while read -r logf; do
          echo ">>> ${logf}"
          tail -40 "${logf}" 2>/dev/null
          echo
        done
    # Archive every logs/ directory alongside the SLURM logs for later inspection.
    ARCHIVE="logs/worker_logs_${SLURM_ARRAY_JOB_ID}_${SLURM_ARRAY_TASK_ID}.tar.gz"
    if find "${PROJECT_DIR}" -type d -name logs -print -quit 2>/dev/null | grep -q .; then
      find "${PROJECT_DIR}" -type d -name logs -print0 2>/dev/null \
        | tar --null -czf "${ARCHIVE}" --files-from=- 2>/dev/null \
        && echo "Archived worker logs to ${ARCHIVE}" \
        || echo "(failed to archive worker logs)"
    else
      echo "(no logs/ directories found under ${PROJECT_DIR})"
    fi
  else
    echo "(no fuzzware project dir at ${PROJECT_DIR} — pipeline likely failed before workers started)"
  fi

  echo "===================== END DIAGNOSTICS (${ACCT_ID}) ====================="
fi

exit ${EXIT_CODE}


