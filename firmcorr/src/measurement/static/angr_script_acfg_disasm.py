import angr
import cle
import argparse
import logging
import networkx as nx
import pyvex
import json
import os
import csv
import time
from base64 import b64encode

log = logging.getLogger(__name__)


def save_callgraph(cfg, ofp):
    """Given an angr CFG, save a call graph in DOT format.
    Keyword Arguments:
    cfg -- angr CFG.
    ofp -- Output filepath.
    """
    try:
        nx.nx_agraph.write_dot(cfg.functions.callgraph, ofp)
    except Exception as ex:
        log.error("Failed to save call graph: %s" % str(ex))

def save_funcs_file(cfg, csv_ofp):
    """Generate a functions CSV based on the provided CFG, and save it to
    csv_ofp."""
    proj_name = os.path.basename(cfg.project.loader.main_object.binary)

    try:
        with open(csv_ofp, "w") as ofile:
            fieldnames = ["firmware", "fva", "func_name"]
            writer = csv.DictWriter(ofile, fieldnames=fieldnames)
            writer.writeheader()

            for func_addr in cfg.kb.functions:
                func_obj = cfg.kb.functions[func_addr]

                # skip functions that don't contain code
                if func_obj.is_simprocedure or func_obj.is_plt or func_obj.is_syscall:
                    continue

                writer.writerow(
                    {
                        "firmware": proj_name,
                        "fva": func_addr,
                        "func_name": func_obj.name,
                    }
                )
    except Exception as ex:
        log.error("Failed to save functions: %s" % str(ex))

def _generate_bb(bb):
    """Generate the basic_blocks dict for one basic block"""
    # fetch elements for basic_blocks
    bb_mnems = [insn.mnemonic for insn in bb.capstone.insns]
    bb_heads = [insn.address for insn in bb.capstone.insns]
    bb_disasm = [
        "%s %s" % (insn.mnemonic, insn.op_str.replace(" ", ""))
        for insn in bb.capstone.insns
    ]
    bb_norm = [
        "%s_%s" % (insn.mnemonic, insn.op_str.replace(" ", ""))
        for insn in bb.capstone.insns
    ]
    bb_len = bb.size
    b64_bytes = b64encode(bb.bytes).decode("ascii")

    return [
        str(bb.addr),
        {
            "bb_mnems": bb_mnems,
            "bb_heads": bb_heads,
            "bb_disasm": bb_disasm,
            "bb_norm": bb_norm,
            "bb_len": bb_len,
            "b64_bytes": b64_bytes,
        },
    ]


def generate_acfg(cfg, json_ofp):
    """Generate an ACFG from the provided CFGFast and write it as a JSON to the filepath
    json_ofp."""
    # binary basename
    binary_name = os.path.basename(cfg.project.loader.main_object.binary)
    # result that will be dumped into the JSON output file
    acfg = {binary_name: {}}

    for func_addr in cfg.kb.functions:
        func_obj = cfg.kb.functions[func_addr]
        func_key = str(func_addr)

        # skip functions that don't contain code
        if func_obj.is_simprocedure or func_obj.is_plt or func_obj.is_syscall:
            continue

        acfg[binary_name][func_key] = {
            "edges": [[src.addr, dst.addr] for src, dst in func_obj.graph.edges],
            "basic_blocks": dict([_generate_bb(bb) for bb in func_obj.blocks]),
            "nodes": list(set([bb.addr for bb in func_obj.blocks])),
            "elapsed_time": 0,
        }

    with open(json_ofp, "w") as ofile:
        ofile.write(json.dumps(acfg, indent=4))


def save_angr_summary(json_ofp, binary_name="", disassembly_success=0, cfg=None, runtime_seconds=0.0):
    """Save key angr analysis summary fields into a JSON file.

    If disassembly did not succeed, counts remain at zero.
    """
    summary = {
        "binary_name": binary_name,
        "disassembly_success": disassembly_success,
        "num_functions": 0,
        "num_edges": 0,
        "num_blocks": 0,
        "runtime_seconds": runtime_seconds,
    }

    if disassembly_success and cfg is not None:
        summary["binary_name"] = os.path.basename(cfg.project.loader.main_object.binary)
        valid_functions = [
            func_obj
            for func_obj in cfg.kb.functions.values()
            if not (func_obj.is_simprocedure or func_obj.is_plt or func_obj.is_syscall)
        ]
        callgraph = cfg.functions.callgraph
        valid_func_addrs = {func.addr for func in valid_functions}
        edge_count = sum(
            1 for src, dst, *_ in callgraph.edges if src in valid_func_addrs and dst in valid_func_addrs
        )
        node_count = sum(len({bb.addr for bb in func.blocks}) for func in valid_functions)

        summary["num_functions"] = len(valid_functions)
        summary["num_edges"] = edge_count
        summary["num_blocks"] = node_count

    with open(json_ofp, "w") as ofile:
        ofile.write(json.dumps(summary, indent=4, sort_keys=True))

def main():
    ## entry point of this program
    ## Parsing the arguments
    parser = argparse.ArgumentParser(description="Tool Options")
    # firmware
    parser.add_argument("FM", default="", type=str, help="Path to firmware binary file")
    parser.add_argument("OD", default="./", type=str, help="Output directory for results")
    parser.add_argument("AR", default="armcortexm", type=str, help="Architecture of the firmware (e.g., armcortexm, mips, x86, etc.)")
    parser.add_argument("BA", default="0x100000", type=str, help="Base address of the module")

    args = parser.parse_args()
    firmware_path = args.FM
    base_addr = args.BA
    output_dir = args.OD
    architecture = args.AR
    binary_name = os.path.basename(firmware_path)
    analysis_start_time = time.time()

    # Auto-detect architecture

    try:
        proj = angr.Project(firmware_path, auto_load_libs=False)
        log.info(f"Loaded {firmware_path} as ELF")
    except Exception as e:
        log.warning(f"ELF load failed: {e}. Trying Blob...")
        try:
            with open(firmware_path, "rb") as ibin:
                blob = cle.Blob(
                    binary=firmware_path,
                    binary_stream=ibin,
                    is_main_bin=True,
                    arch=architecture,
                    base_addr=int(base_addr, 16),
                )
            log.warning("Creating angr project")
            proj = angr.Project(thing=blob, use_sim_procedures=False)
            log.info(f"Loaded {firmware_path} as Blob.")
        except Exception as e2:
            log.error(f"Failed loading firmware: {e2}")
            save_angr_summary(
                os.path.join(output_dir, "angr.json"),
                binary_name=binary_name,
                disassembly_success=0,
                runtime_seconds=time.time() - analysis_start_time,
            )
            return
    
    try:
        cfg = proj.analyses.CFGFast(
            normalize=True,
            data_references=True,
            cross_references=False,

            # Function recovery control
            force_complete_scan=False,

            # Indirect flow (KEY for fairness)
            resolve_indirect_jumps=False,

            # Heuristics & noise control
            detect_tail_calls=False, # recommended for Cortex-M benchmar
            # detect_tail_calls_threshold=3,
            # detect_function_prologues=True,

            # CFG structure quality
            start_at_entry=True,
            symbols=True,

            # Avoid speculative explosion
            skip_unmapped_addrs=True,
            exclude_sparse_regions=True,
            
            show_progressbar=True
        )
    except Exception as e2:
        log.error(f"Failed disassembling firmware: {e2}")
        save_angr_summary(
            os.path.join(output_dir, f"{binary_name}_angr.json"),
            binary_name=binary_name,
            disassembly_success=0,
            runtime_seconds=time.time() - analysis_start_time,
        )
        return

    log.warning("Saving Functions")
    save_funcs_file(cfg, os.path.join(output_dir, f"{binary_name}_angr_functions.csv"))

    log.warning("Saving call graph")
    save_callgraph(cfg, os.path.join(output_dir, f"{binary_name}_angr_call_graph.dot"))

    log.warning("Saving ACFG")
    generate_acfg(cfg, os.path.join(output_dir, f"{binary_name}_angr_acfg.json"))

    log.warning("Saving angr summary")
    save_angr_summary(
        os.path.join(output_dir, f"{binary_name}_angr.json"),
        binary_name=binary_name,
        disassembly_success=1,
        cfg=cfg,
        runtime_seconds=time.time() - analysis_start_time,
    )

if __name__ == "__main__":
    main()

