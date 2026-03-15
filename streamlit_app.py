"""
streamlit_app.py — Timetable Generator (Streamlit) v4.1

Architecture (refactored):
  • generator.py  — TimetableEngine: pure scheduling/generation logic
  • input.py      — Steps 1, 2, 3 UI pages + shared helper utilities
  • streamlit_app.py (this file) — app bootstrap, Step 4 / Generate / Final Timetable
"""

import io
import json
import logging
import traceback
import hashlib
from datetime import datetime

import streamlit as st

# ── Import engine and all step 1/2/3 UI components ───────────────────────────
from generator import TimetableEngine
from timetable_validator import validate_timetable
from input import (
    # Shared helpers
    DAY_NAMES, log as _input_log,
    _get_eng, _nav, _notify, _show_notifications,
    _file_hash, _already_processed, _all_classes,
    _json_download, _header, _show_upload_error_if_any,
    # Input step pages
    page_step1, page_step2, page_step3,
)


# ─────────────────────────────────────────────────────────────────────────────
#  LOGGING
# ─────────────────────────────────────────────────────────────────────────────
class _MemHandler(logging.Handler):
    """Keeps last N log lines in memory for the sidebar debug console."""
    MAX = 500
    def __init__(self):
        super().__init__()
        self.lines = []
    def emit(self, record):
        self.lines.append(self.format(record))
        if len(self.lines) > self.MAX:
            self.lines = self.lines[-self.MAX:]

_LOG_FMT = "[%(levelname)s] %(filename)s:%(funcName)s:%(lineno)d — %(message)s"
_mem_handler = _MemHandler()
_mem_handler.setFormatter(logging.Formatter(_LOG_FMT))

logging.basicConfig(level=logging.DEBUG, format=_LOG_FMT,
                    handlers=[logging.StreamHandler(), _mem_handler], force=True)
log = logging.getLogger("timetable")
log.info("streamlit_app module loaded")


# ─────────────────────────────────────────────────────────────────────────────
#  Page config
# ─────────────────────────────────────────────────────────────────────────────
st.set_page_config(page_title="Timetable Generator", page_icon="📅",
                   layout="wide", initial_sidebar_state="collapsed")


# ─────────────────────────────────────────────────────────────────────────────
#  Session-state bootstrap
# ─────────────────────────────────────────────────────────────────────────────
_ENGINE_VERSION = "4.1"


def _engine_is_stale(obj) -> bool:
    if obj is None:
        return True
    if getattr(obj, "ENGINE_VERSION", None) != _ENGINE_VERSION:
        return True
    if not callable(getattr(obj, "run_full_generation", None)):
        return True
    return False


def _init_state():
    defaults = {
        "page":              "step1",
        "ni_ppd":            7,
        "ni_wdays":          6,
        "ni_fhalf":          4,
        "ni_shalf":          3,
        "s1_teachers":       [],
        "s1_teacher_fname":  "",
        "s1_sections":       {cls: 4 for cls in range(6, 13)},
        "_upload_hash":      {},
        "_s1_pending_raw":   None,
        "_s1_pending_hash":  None,
        "_s1_pending_name":  None,
        "s4_stage":          0,
        "s4_s1_status":      None,
        "s4_s3_status":      None,
        "s4_ff_result":      None,
        "gen_result":        None,
        "ta_allocation":     None,
        "ta_group_slots":    None,
        "ta_all_rows":       None,
        "ta2_allocation":    None,
        "relaxed_consec":    set(),
        "relaxed_main":      set(),
        "s2_validation_result": None,
        "s3_validation_result": None,
        "validation_result": None,
        "s1_validated":      False,
        "s2_validated":      False,
        "s3_validated":      False,
        "_s2_show_error_popup": False,
        "_s3_show_error_popup": False,
        "_notify":           [],
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

    if "engine" not in st.session_state:
        st.session_state["engine"] = TimetableEngine()
        log.info("_init_state: fresh engine created")
    elif _engine_is_stale(st.session_state["engine"]):
        log.warning("_init_state: stale engine detected — resetting")
        st.session_state["engine"]       = TimetableEngine()
        st.session_state["page"]         = "step1"
        st.session_state["s1_validated"] = False
        st.session_state["s2_validated"] = False
        st.session_state["s3_validated"] = False
        st.session_state["gen_result"]   = None

    log.debug("_init_state: done  page=%s  s1v=%s",
              st.session_state.get("page"), st.session_state.get("s1_validated"))


_init_state()


# ─────────────────────────────────────────────────────────────────────────────
#  Generate-page helpers
# ─────────────────────────────────────────────────────────────────────────────
PAGE_LABELS = {
    "step1":           "Step 1 — Basic Config",
    "step2":           "Step 2 — Class Assignments",
    "step3":           "Step 3 — Teacher Settings",
    "generate":        "Step 4 — Generate",
    "final_timetable": "Final Timetable",
}


def _excel_download(mode: str, label: str):
    log.info("_excel_download: mode=%s", mode)
    
    # Check validation status
    val_result = st.session_state.get("validation_result", {})
    if val_result and not val_result.get("valid"):
        st.error("❌ Cannot download — Validation failed. Regenerate timetable first.")
        return
    
    try:
        xbytes = _get_eng().get_excel_bytes(mode)
        fname  = f"{mode}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        st.download_button(label=label, data=xbytes, file_name=fname,
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                           use_container_width=True)
        log.info("_excel_download: ready %s (%d bytes)", fname, len(xbytes))
    except Exception as ex:
        log.error("_excel_download: %s\n%s", ex, traceback.format_exc())
        st.error(f"Export error: {ex}")


# ═════════════════════════════════════════════════════════════════════════════
#  GENERATE PAGE  (fully automatic)
# ═════════════════════════════════════════════════════════════════════════════
def page_generate():
    eng = _get_eng()

    if not eng.configuration:
        st.warning("⚠ Step 1 not yet completed — basic configuration is missing.")
        st.info("Please complete Step 1 (Basic Config) before continuing.")
        if st.button("← Go to Step 1", type="primary", key="gen_guard_back"):
            _nav("step1")
        return

    log.info("page_generate: render")
    cfg   = eng.configuration
    ppd   = cfg.get("periods_per_day", "?")
    wdays = cfg.get("working_days", "?")
    _header("🚀 Generating Timetable",
            f"{wdays} days/week · {ppd} periods/day — fully automatic")
    _show_notifications()

    col_back, _spacer = st.columns([1, 2])
    with col_back:
        if st.button("← Back to Step 3"):
            _nav("step3")

    gen_result = st.session_state.get("gen_result")

    # ── RUN ─────────────────────────────────────────────────────────────────
    if gen_result is None:
        st.info("Click **Generate** to produce the complete timetable automatically.\n\n"
                "The engine will run all stages, apply backtracking, and—if needed—"
                "automatically reduce over-constrained subjects by 1 period to resolve "
                "deadlocks.")

        if st.button("⚡ Generate Timetable", type="primary",
                     key="gen_run_btn", use_container_width=True):
            log.info("page_generate: starting full generation")
            progress_placeholder = st.empty()
            progress_log = []

            def _progress(msg):
                if isinstance(msg, tuple):
                    msg = msg[0]
                msg = str(msg)
                progress_log.append(msg)
                if msg.strip():
                    lines = [m for m in progress_log[-6:] if m.strip()]
                    progress_placeholder.info("⏳  " + "\n\n".join(lines))

            with st.spinner("🚀 Generating timetable — please wait…"):
                try:
                    result = eng.run_full_generation(progress_cb=_progress)
                    st.session_state["gen_result"] = result
                    log.info("page_generate: done ok=%s remaining=%s",
                             result["ok"], result["remaining"])
                    
                    # ── VALIDATION CHECKPOINT ──
                    if result["ok"]:
                        log.info("page_generate: running validation checks")
                        is_valid, errors, warnings, report = validate_timetable(eng)
                        st.session_state["validation_result"] = {
                            "valid": is_valid,
                            "errors": errors,
                            "warnings": warnings,
                            "report": report
                        }
                        
                        if is_valid:
                            _notify("✅ Timetable generated — validation PASSED!", "success")
                        else:
                            _notify(f"❌ Validation FAILED: {len(errors)} error(s)", "error")
                    else:
                        _notify(
                            f"⚠ Timetable generated with {result['remaining']} "
                            f"period(s) unplaced. See details below.", "warning")
                        st.session_state["validation_result"] = {
                            "valid": False,
                            "errors": [f"{result['remaining']} periods unplaced"],
                            "warnings": [],
                            "report": ""
                        }
                except Exception as ex:
                    log.error("page_generate: %s\n%s", ex, traceback.format_exc())
                    _notify(f"Generation error: {ex}", "error")
                    st.session_state["validation_result"] = {
                        "valid": False,
                        "errors": [str(ex)],
                        "warnings": [],
                        "report": ""
                    }

            progress_placeholder.empty()
            st.rerun()
        return

    # ── RESULT ──────────────────────────────────────────────────────────────
    remaining   = gen_result.get("remaining", 0)
    overloaded  = gen_result.get("overloaded", [])
    blocked     = gen_result.get("blocked_only", [])
    reductions  = gen_result.get("period_reductions", [])
    prog_log    = gen_result.get("progress_log", [])
    wdays_r     = gen_result.get("wdays", "?")
    ppd_r       = gen_result.get("ppd", "?")
    total_slots = gen_result.get("total_slots", "?")

    if remaining == 0:
        st.success("✅ **Timetable is 100% complete — all periods placed!**")
    else:
        st.error(f"⚠  **{remaining} period(s) could not be placed.**  "
                 f"The timetable is as complete as possible given the constraints.")

    # ── VALIDATION REPORT ──
    val_result = st.session_state.get("validation_result", {})
    if val_result:
        val_report = val_result.get("report", "")
        if val_report:
            if val_result.get("valid"):
                st.info("✅ **Validation Report:**\n\n" + val_report)
            else:
                st.error("❌ **Validation Failed - Issues Found:**\n\n" + val_report)
        
        # Block downloads if validation failed
        val_errors = val_result.get("errors", [])
        if val_errors:
            st.warning(
                "⚠️ **Cannot download Excel files** — Timetable validation failed. "
                "Please review the issues above and regenerate the timetable."
            )


    if reductions:
        with st.expander(f"📉 Period Reductions Applied ({len(reductions)})",
                         expanded=True):
            st.caption(
                "The engine automatically reduced these subjects by 1 period/week "
                "to break deadlocks. You may want to review these in Step 2.")
            for r in reductions:
                st.warning(
                    f"**{r['subject']}** in **{r['class']}** "
                    f"(teacher: {r['teacher']})  —  "
                    f"{r['from_periods']} → {r['to_periods']} periods/week")

    if overloaded:
        st.markdown("#### ❌ Overloaded Teachers")
        st.caption(f"Grid capacity: {wdays_r} × {ppd_r} = {total_slots} slots")
        for tname, assigned, cap, excess, unp in overloaded:
            st.container(border=True)
            col1, col2 = st.columns([2, 3])
            with col1: st.markdown(f"**❌ {tname}**")
            with col2:
                st.markdown(f"Assigned: **{assigned}** | Capacity: **{cap}** "
                            f"| Excess: **+{excess}** | Unplaced: **{unp}**")

    if blocked:
        st.markdown("#### ⚠ Blocked Teachers *(capacity OK, but all slots clash)*")
        for tname, assigned, cap, unp in blocked:
            with st.container(border=True):
                col1, col2 = st.columns([2, 3])
                with col1: st.markdown(f"**⚠ {tname}**")
                with col2:
                    st.markdown(f"Assigned: **{assigned} / {cap}** | Unplaced: **{unp}**")

    st.divider()
    col_view, col_rerun = st.columns(2)
    with col_view:
        if st.button("📊 View Final Timetable →", type="primary",
                     use_container_width=True, key="gen_view_btn"):
            _nav("final_timetable")
    with col_rerun:
        if st.button("🔄 Re-run Generation", use_container_width=True,
                     key="gen_rerun_btn"):
            st.session_state["gen_result"] = None
            st.rerun()

    if prog_log:
        with st.expander("📋 Generation Log", expanded=False):
            log_lines = [
                (m[0] if isinstance(m, tuple) else str(m))
                for m in prog_log
            ]
            st.code("\n".join(log_lines), language="")


# ═════════════════════════════════════════════════════════════════════════════
#  STEP 4  (manual mode — power users)
# ═════════════════════════════════════════════════════════════════════════════
def page_step4():
    eng = _get_eng()
    log.info("page_step4: render stage=%d", st.session_state.get("s4_stage",0))
    cfg   = eng.configuration
    ppd   = cfg["periods_per_day"]
    wdays = cfg["working_days"]
    _header("📅 Step 4: Generate Timetable",
            f"{wdays} days/week · {ppd} periods/day · {wdays*ppd} slots/week per class")
    _show_notifications()
    if st.button("← Back to Step 3"): _nav("step3")
    st.divider()

    stage   = st.session_state.get("s4_stage",0)
    s1_stat = st.session_state.get("s4_s1_status")

    with st.container(border=True):
        st.markdown("**Stage 1 — HC1/HC2: Place Class-Teacher & Fixed/Preference Periods**")
        if stage == 0:
            if st.button("▶ Run Stage 1", type="primary", key="s4_run_s1"):
                log.info("page_step4: Run Stage 1")
                with st.spinner("Running Stage 1…"):
                    try:
                        result = eng.run_stage1()
                        st.session_state.update({"s4_s1_status":result,"s4_stage":1})
                        eng._relaxed_consec_keys = set()
                        eng._relaxed_main_keys   = set()
                        log.info("page_step4: Stage 1 done has_issues=%s", result.get("has_issues"))
                        _notify("Stage 1 complete.","success")
                    except Exception as ex:
                        log.error("page_step4 stage1: %s\n%s", ex, traceback.format_exc())
                        _notify(f"Stage 1 error: {ex}","error")
                st.rerun()
        else:
            if s1_stat:
                bg   = s1_stat.get("stage_bg","#1a7a1a")
                stxt = s1_stat.get("stage_txt","Stage 1 done")
                st.markdown(f"<div style='background:{bg};color:white;padding:8px 16px;"
                            f"border-radius:4px;font-weight:bold'>{stxt}</div>",
                            unsafe_allow_html=True)
                st.info(s1_stat.get("status",""))
            c1,c2 = st.columns(2)
            with c1:
                if st.button("📋 Task Analysis →", type="primary", key="s4_ta_btn"):
                    log.info("page_step4: → task_analysis")
                    eng._relaxed_consec_keys = set(st.session_state.get("relaxed_consec",set()))
                    eng._relaxed_main_keys   = set(st.session_state.get("relaxed_main",set()))
                    _nav("task_analysis")
            with c2:
                if st.button("↺ Re-run Stage 1", key="s4_rerun_s1"):
                    log.info("page_step4: re-run Stage 1")
                    for k in ("s4_stage","s4_s1_status","ta_allocation","ta2_allocation","s4_s3_status"):
                        st.session_state[k] = 0 if k=="s4_stage" else None
                    st.rerun()

    if stage >= 1 and eng._timetable:
        st.divider()
        st.markdown("**Stage 1 Preview**")
        _render_timetable_tabs(eng._timetable, key_prefix="s4")
        st.divider()
        st.markdown("**Export Stage 1 snapshot**")
        c1,c2 = st.columns(2)
        with c1: _excel_download("class","📥 Class Timetables")
        with c2: _excel_download("teacher","📥 Teacher Timetables")


# ═════════════════════════════════════════════════════════════════════════════
#  TASK ANALYSIS
# ═════════════════════════════════════════════════════════════════════════════
def page_task_analysis():
    eng = _get_eng()
    log.info("page_task_analysis: render")
    _header("📋 Task Analysis","Review groups before Stage 2. Allocate period slots.")
    _show_notifications()
    nav1,nav2 = st.columns(2)
    with nav1:
        if st.button("← Back to Stage 1"): _nav("step4")
    with nav2:
        if st.button("🗓 Allocate Periods", type="primary", key="ta_alloc_btn"):
            log.info("page_task_analysis: allocating")
            with st.spinner("Allocating…"):
                try:
                    slots, allocation, rows = eng._run_task_analysis_allocation()
                    st.session_state.update({"ta_allocation":allocation,"ta_group_slots":slots,"ta_all_rows":rows})
                    eng._last_allocation  = allocation
                    eng._last_group_slots = slots
                    eng._last_all_rows    = rows
                    ok_n = sum(1 for ar in allocation.values() if ar.get("ok"))
                    log.info("page_task_analysis: done %d ok / %d total", ok_n, len(allocation))
                    _notify(f"✓ {ok_n} OK, {len(allocation)-ok_n} failed.",
                            "success" if ok_n==len(allocation) else "warning")
                except Exception as ex:
                    log.error("page_task_analysis: %s\n%s", ex, traceback.format_exc())
                    _notify(f"Allocation error: {ex}","error")
            st.rerun()

    allocation  = st.session_state.get("ta_allocation")
    group_slots = st.session_state.get("ta_group_slots")
    all_rows    = st.session_state.get("ta_all_rows")

    if allocation:
        all_ok = all(ar.get("ok",False) for ar in allocation.values())
        if all_ok:
            if st.button("▶ Proceed to Stage 2 →", type="primary", key="ta_proceed"):
                log.info("page_task_analysis: → task_analysis2")
                _nav("task_analysis2")
        else:
            st.error("Some groups failed — relax constraints or fix Step 2.")

    _show_notifications()
    if all_rows is None:
        st.info("Click **Allocate Periods** to compute slot assignments.")
        try:
            _, _, rows = eng._run_task_analysis_allocation()
            _render_ta_table(rows, None, None)
        except Exception as ex:
            log.warning("page_task_analysis: preview error: %s", ex)
    else:
        _render_ta_table(all_rows, group_slots, allocation)


def _render_ta_table(all_rows, group_slots, allocation):
    eng = _get_eng()
    log.debug("_render_ta_table: %d rows", len(all_rows) if all_rows else 0)
    if not all_rows:
        st.info("No parallel/combined/consecutive groups found."); return
    DAYS_A = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"]
    sections = {"A":"Combined Groups","B":"Standalone Parallel Pairs","C":"Consecutive Groups"}
    for sec, sec_title in sections.items():
        sec_rows = [r for r in all_rows if r.get("section")==sec]
        if not sec_rows: continue
        st.markdown(f"#### {sec_title}")
        groups = {}
        for r in sec_rows: groups.setdefault(r["group"],[]).append(r)
        for gn, grows in sorted(groups.items()):
            first = grows[0]
            cls_s = ", ".join(r["class"] for r in grows)
            slot_info = ""
            if group_slots and gn in group_slots:
                gs = group_slots[gn]
                slot_info = f"  ·  **{gs['slots']} slot(s)**" if gs.get("ok") else f"  ·  ⚠ {gs.get('reason','?')}"
            alloc_info = ""; alloc_ok = False
            if allocation and gn in allocation:
                ar = allocation[gn]; alloc_ok = ar.get("ok",False)
                if alloc_ok:
                    placed = ar.get("placed", ar.get("slots",[]))
                    ps = "  ·  ".join(f"{DAYS_A[d]} P{p+1}" for d,p in sorted(placed)) if placed else "placed"
                    alloc_info = f"✅ {ps}"
                else:
                    alloc_info = f"❌ {ar.get('remaining','?')} unplaced. {ar.get('reason','')}"
            icon = "🟢" if (allocation and alloc_ok) else ("🔴" if allocation else "⚪")
            with st.expander(f"{icon} **Group {gn}** — {cls_s} · {first['subject']} / {first['teacher']}{slot_info}", expanded=False):
                for r in grows:
                    par = (f"  ‖  Parallel: {r['par_subj']} / {r['par_teacher']}"
                           if r.get("par_subj") not in ("—","?","",None) else "")
                    st.write(f"  📌 **{r['class']}** — {r['subject']} / {r['teacher']}{par}")
                if alloc_info:
                    if "✅" in alloc_info: st.success(alloc_info)
                    else:                  st.error(alloc_info)
                if sec=="C":
                    rk = (first["class"], first["subject"])
                    rel = st.session_state.get("relaxed_consec",set())
                    is_rel = rk in rel
                    if st.button("🔓 Un-relax" if is_rel else "🔒 Relax to Filler", key=f"relax_c_{gn}"):
                        for r in grows:
                            k = (r["class"],r["subject"])
                            if is_rel: rel.discard(k); eng._relaxed_consec_keys.discard(k)
                            else:      rel.add(k);     eng._relaxed_consec_keys.add(k)
                        st.session_state["relaxed_consec"] = rel
                        log.info("_render_ta_table: group %s relax=%s", gn, not is_rel)
                        st.rerun()


# ═════════════════════════════════════════════════════════════════════════════
#  TASK ANALYSIS 2
# ═════════════════════════════════════════════════════════════════════════════
def page_task_analysis2():
    eng = _get_eng()
    log.info("page_task_analysis2: render")
    _header("📋 Task Analysis — Stage 2","Allocate remaining slots before Stage 3.")
    _show_notifications()
    eng._relaxed_consec_keys = set(st.session_state.get("relaxed_consec",set()))
    eng._relaxed_main_keys   = set(st.session_state.get("relaxed_main",set()))
    nav1,nav2 = st.columns(2)
    with nav1:
        if st.button("← Back to Task Analysis"): _nav("task_analysis")
    with nav2:
        if st.button("🗓 Allocate Slots", type="primary", key="ta2_alloc_btn"):
            log.info("page_task_analysis2: allocating")
            with st.spinner("Allocating Stage 2 slots…"):
                try:
                    result = eng._run_ta2_allocation()
                    st.session_state["ta2_allocation"] = result
                    eng._last_ta2_allocation = result
                    ok_n = sum(1 for ar in result.values() if isinstance(ar,dict) and ar.get("remaining",1)==0)
                    log.info("page_task_analysis2: done %d ok", ok_n)
                    _notify(f"✓ Stage 2 done: {ok_n} groups OK.","success")
                except Exception as ex:
                    log.error("page_task_analysis2: %s\n%s", ex, traceback.format_exc())
                    _notify(f"Error: {ex}","error")
            st.rerun()

    ta2 = st.session_state.get("ta2_allocation")
    if ta2:
        fails = [k for k,ar in ta2.items() if isinstance(ar,dict) and ar.get("remaining",1)>0]
        if not fails:
            st.success("✅ All groups allocated.")
            if st.button("📅 Proceed to Stage 3 →", type="primary", key="ta2_proceed"):
                log.info("page_task_analysis2: → stage2_page")
                _nav("stage2_page")
        else:
            st.warning(f"⚠ {len(fails)} group(s) have unplaced periods.")
            if st.button("📅 Proceed to Stage 3 anyway →", key="ta2_proceed_any"):
                log.info("page_task_analysis2: proceed with %d failures", len(fails))
                _nav("stage2_page")
        _render_ta2_table(ta2)
    else:
        st.info("Click **Allocate Slots** to compute allocations.")


def _render_ta2_table(result):
    log.debug("_render_ta2_table: %d groups", len(result) if result else 0)
    if not result: return
    DAYS_A = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"]
    def slot_str(placed):
        return "  ·  ".join(f"{DAYS_A[d]} P{p+1}" for d,p in sorted(placed)) if placed else "—"
    for gn, ar in sorted(result.items()):
        if not isinstance(ar,dict): continue
        placed    = ar.get("slots", ar.get("placed",[]))
        remaining = ar.get("remaining",0)
        ok        = remaining == 0
        with st.expander(f"{'✅' if ok else '❌'} Group {gn}", expanded=not ok):
            c1,c2 = st.columns(2)
            with c1:
                st.metric("Total",          ar.get("total","?"))
                st.metric("Stage 1 placed", ar.get("s1_placed","?"))
            with c2:
                st.metric("Stage 2 placed", ar.get("new_placed","?"))
                st.metric("Remaining",      remaining)
            if placed: st.success(f"Slots: {slot_str(placed)}")
            if not ok:
                st.error(f"Reason: {ar.get('reason','unknown')}")
                rel = st.session_state.get("relaxed_main",set()); k_str = str(gn)
                if st.button("🔓 Un-relax" if k_str in rel else "🔒 Relax to Filler", key=f"relax_m_{gn}"):
                    rel.discard(k_str) if k_str in rel else rel.add(k_str)
                    st.session_state["relaxed_main"] = rel
                    log.info("_render_ta2_table: group %s main-relax=%s", gn, k_str in rel)
                    st.rerun()


# ═════════════════════════════════════════════════════════════════════════════
#  STAGE 2 PAGE
# ═════════════════════════════════════════════════════════════════════════════
def _render_force_fill_summary(ff_result):
    """Render the Force Fill result summary."""
    remaining   = ff_result.get("remaining", 0)
    relaxed     = ff_result.get("relaxed")
    overloaded  = ff_result.get("overloaded", [])
    blocked     = ff_result.get("blocked_only", [])
    wdays       = ff_result.get("wdays", "?")
    ppd         = ff_result.get("ppd", "?")
    total_slots = ff_result.get("total_slots", "?")

    if remaining == 0:
        st.success("✅ All periods placed — timetable is 100% complete!")
        if relaxed:
            with st.expander("ℹ️ Constraints relaxed during Force Fill", expanded=True):
                st.code(relaxed, language="")
        return

    st.error(f"⚠  {remaining} period(s) could not be placed.")

    if overloaded:
        st.markdown("#### ❌ Overloaded Teachers")
        st.caption(f"Total grid capacity: {wdays} days × {ppd} periods = {total_slots} slots per teacher")
        for tname, assigned, cap, excess, unp in overloaded:
            with st.container(border=True):
                col1, col2 = st.columns([2, 3])
                with col1: st.markdown(f"**❌ {tname}**")
                with col2:
                    st.markdown(
                        f"Assigned: **{assigned}** &nbsp;|&nbsp; "
                        f"Capacity: **{cap}** &nbsp;|&nbsp; "
                        f"Excess: **+{excess}** ← fix in Step 2 &nbsp;|&nbsp; "
                        f"Unplaced: **{unp}**")

    if blocked:
        st.markdown("#### ⚠ Blocked Teachers *(within capacity, but slots clash)*")
        for tname, assigned, cap, unp in blocked:
            with st.container(border=True):
                col1, col2 = st.columns([2, 3])
                with col1: st.markdown(f"**⚠ {tname}**")
                with col2:
                    st.markdown(f"Assigned: **{assigned} / {cap}** &nbsp;|&nbsp; Unplaced: **{unp}**")

    if not overloaded and not blocked:
        st.info("Could not identify a specific cause. Please review teacher workloads in Step 2.")

    if relaxed:
        with st.expander("ℹ️ Constraints relaxed during Force Fill", expanded=False):
            st.code(relaxed, language="")


def page_stage2():
    eng = _get_eng()
    log.info("page_stage2: render")
    _header("⚙ Stage 2 — Fill Remaining Periods",
            "Stage 3 of engine: consecutive pairs, daily subjects, fillers and repair.")
    _show_notifications()
    if st.button("← Back to Task Analysis 2"): _nav("task_analysis2")

    s3_status  = st.session_state.get("s4_s3_status")
    ff_result  = st.session_state.get("s4_ff_result")

    if s3_status is None:
        st.info("Click **Run Stage 3** to fill all remaining empty slots.")
        if st.button("▶ Run Stage 3", type="primary", key="s2pg_run"):
            log.info("page_stage2: Run Stage 3")
            with st.spinner("Running Stage 3 — filling remaining periods…"):
                try:
                    result = eng.run_stage3()
                    st.session_state.update({"s4_s3_status": result, "s4_stage": 3,
                                             "s4_ff_result": None})
                    log.info("page_stage2: Stage 3 done ok=%s unplaced=%s",
                             result.get("ok"), result.get("unplaced"))
                    _notify(result.get("msg", "Stage 3 complete."),
                            "success" if result.get("ok") else "warning")
                except Exception as ex:
                    log.error("page_stage2 stage3: %s\n%s", ex, traceback.format_exc())
                    _notify(f"Stage 3 error: {ex}", "error")
            st.rerun()
        return

    if s3_status.get("ok"):
        st.success(s3_status.get("msg", "✅ Complete!"))
    else:
        st.warning(s3_status.get("msg", ""))

    unplaced_after_s3 = s3_status.get("unplaced", 0)

    col_view, col_rerun, col_ff = st.columns([2, 1, 2])
    with col_view:
        if st.button("📊 View Final Timetable →", type="primary", key="s2pg_view"):
            log.info("page_stage2: → final_timetable")
            _nav("final_timetable")
    with col_rerun:
        if st.button("↺ Re-run Stage 3", key="s2pg_rerun"):
            log.info("page_stage2: re-run")
            st.session_state["s4_s3_status"] = None
            st.session_state["s4_ff_result"] = None
            st.rerun()
    with col_ff:
        if unplaced_after_s3 > 0:
            if st.button("🔧 Force Fill", type="secondary", key="s2pg_ff",
                         help="Min-Conflicts CSP solver — up to 1500 iterations, "
                              "stops as soon as all periods are placed."):
                log.info("page_stage2: running Force Fill")
                progress_placeholder = st.empty()
                progress_msgs = []

                def _progress(msg):
                    progress_msgs.append(msg)
                    if msg:
                        progress_placeholder.info(f"⏳ {msg}")

                with st.spinner("🔧 Force Fill running…"):
                    try:
                        ff = eng.run_force_fill(progress_cb=_progress)
                        st.session_state["s4_ff_result"] = ff
                        st.session_state["s4_s3_status"] = {
                            **s3_status,
                            "unplaced": ff["remaining"],
                            "ok":       ff["ok"],
                            "msg":      ff.get("msg", ""),
                        }
                        log.info("page_stage2: Force Fill done ok=%s remaining=%s",
                                 ff["ok"], ff["remaining"])
                        _notify(
                            "✅ Force Fill complete — all periods placed!" if ff["ok"]
                            else f"⚠ Force Fill done — {ff['remaining']} period(s) still unplaced.",
                            "success" if ff["ok"] else "warning",
                        )
                    except Exception as ex:
                        log.error("page_stage2 force_fill: %s\n%s", ex, traceback.format_exc())
                        _notify(f"Force Fill error: {ex}", "error")
                progress_placeholder.empty()
                st.rerun()

    if ff_result is not None:
        st.divider()
        st.markdown("### 🔧 Force Fill Summary")
        _render_force_fill_summary(ff_result)


# ═════════════════════════════════════════════════════════════════════════════
#  FINAL TIMETABLE
# ═════════════════════════════════════════════════════════════════════════════
def page_final_timetable():
    eng = _get_eng()

    if not eng.configuration:
        st.warning("⚠ Step 1 not yet completed — basic configuration is missing.")
        if st.button("← Go to Step 1", type="primary", key="ft_guard_back"):
            _nav("step1")
        return

    log.info("page_final_timetable: render")
    _header("📊 Final Timetable","View and export the complete timetable.")
    _show_notifications()

    if st.button("← Back to Generate"):
        _nav("generate")

    gen_result = st.session_state.get("gen_result") or {}
    reductions = gen_result.get("period_reductions", [])
    if reductions:
        with st.expander(f"📉 {len(reductions)} period reduction(s) were applied to "
                         f"resolve deadlocks — click to review", expanded=False):
            for r in reductions:
                st.warning(
                    f"**{r['subject']}** in **{r['class']}** "
                    f"(teacher: {r['teacher']})  →  "
                    f"{r['from_periods']} → {r['to_periods']} periods/week")
    tt = eng._timetable
    if not tt:
        st.error("No timetable generated."); log.warning("page_final_timetable: no timetable"); return
    with st.container(border=True):
        st.markdown("**📥 Export to Excel**")
        c1,c2,c3 = st.columns(3)
        with c1: _excel_download("class",             "📥 Class Timetables")
        with c2: _excel_download("consolidated_class","📥 Consolidated Class View")
        with c3: _excel_download("teacher",           "📥 Teacher Timetables")
        c4,c5,c6 = st.columns(3)
        with c4: _excel_download("ct_list",  "📥 CT List")
        with c5: _excel_download("workload", "📥 Workload")
        with c6: _excel_download("one_sheet","📥 One-Sheet")
    st.divider()
    tc, tt2, ts = st.tabs(["🏫 Classwise","👨‍🏫 Teacherwise","📋 Summary"])
    with tc:  _render_class_view(tt)
    with tt2: _render_teacher_view(tt)
    with ts:  _render_summary_view(tt)


# ─────────────────────────────────────────────────────────────────────────────
#  Timetable renderers
# ─────────────────────────────────────────────────────────────────────────────
def _render_timetable_tabs(tt, key_prefix="tt"):
    tc, tt2 = st.tabs(["🏫 Class View","👨‍🏫 Teacher View"])
    with tc:  _render_class_view(tt,   key_prefix=key_prefix+"_c")
    with tt2: _render_teacher_view(tt, key_prefix=key_prefix+"_t")


def _render_class_view(tt, key_prefix="cls"):
    import pandas as pd
    log.debug("_render_class_view: key=%s", key_prefix)
    all_classes = tt["all_classes"]; days = tt["days"]; ppd = tt["ppd"]
    half1 = tt["half1"];             grid = tt["grid"]
    sel_cn = st.selectbox("Select Class", all_classes, key=f"{key_prefix}_sel")
    if not sel_cn: return
    header = ["Day"] + [f"P{p+1}{'①' if p<half1 else '②'}" for p in range(ppd)]
    rows = []
    for d, dname in enumerate(days):
        row = [dname]
        for p in range(ppd):
            g = grid.get(sel_cn,[])
            cell = g[d][p] if d<len(g) and g else None
            if cell:
                subject_str = f"{'★' if cell.get('is_ct') else ''}{cell.get('subject','')}"
                teacher_str = cell.get('teacher','')
                
                # Add parallel information if present
                par_subjects = cell.get("par_subjects", [])
                par_teachers = cell.get("par_teachers", [])
                
                if par_subjects and par_teachers:
                    # New format with multiple parallels - show as co-equal
                    # Build combined string with all subjects and all teachers
                    all_subjects = [subject_str] + [f"{'★' if cell.get('is_ct') else ''}{ps}" for ps in par_subjects]
                    all_teachers = [teacher_str] + par_teachers
                    
                    subjects_line = "/".join(all_subjects)
                    teachers_line = "/".join(all_teachers)
                    row.append(f"{subjects_line}\n{teachers_line}")
                else:
                    # Old format or no parallels
                    par_teach = cell.get("par_teach", "")
                    par_subj = cell.get("par_subj", "")
                    if par_teach and par_teach not in ("—", "?"):
                        row.append(f"{subject_str}/{teacher_str}\n(‖ {par_subj}/{par_teach})")
                    else:
                        row.append(f"{subject_str}/{teacher_str}")
            else:
                row.append("—")
        rows.append(row)
    st.dataframe(pd.DataFrame(rows, columns=header), use_container_width=True, hide_index=True)


def _render_teacher_view(tt, key_prefix="tch"):
    import pandas as pd
    log.debug("_render_teacher_view: key=%s", key_prefix)
    all_classes = tt["all_classes"]; days = tt["days"]; ppd = tt["ppd"]; grid = tt["grid"]
    tg = {}
    for cn in all_classes:
        g = grid.get(cn,[])
        for d in range(len(days)):
            if d >= len(g): continue
            for p in range(ppd):
                cell = g[d][p]
                if not cell: continue
                etype = cell.get("type", "normal")
                cc    = cell.get("combined_classes", [])
                is_combined = bool(cc) and etype in ("combined", "combined_parallel")

                tname = cell.get("teacher", "")
                sname = cell.get("subject", "")
                if tname and tname not in ("—", "?"):
                    if is_combined:
                        if not cc or cn == cc[0]:
                            cls_label = "+".join(cc)
                            tg.setdefault(tname, [[None]*ppd for _ in range(len(days))])
                            tg[tname][d][p] = {"class": cls_label, "subject": sname,
                                               "is_ct": cell.get("is_ct", False)}
                    else:
                        tg.setdefault(tname, [[None]*ppd for _ in range(len(days))])
                        tg[tname][d][p] = {"class": cn, "subject": sname,
                                           "is_ct": cell.get("is_ct", False)}

                # Handle both old format (par_teach/par_subj) and new format (par_teachers/par_subjects)
                pt = cell.get("par_teach", "")
                ps = cell.get("par_subj", "")
                par_teachers = cell.get("par_teachers", []) or []  # Ensure it's always a list
                par_subjects = cell.get("par_subjects", []) or []  # Ensure it's always a list
                
                # NEW FORMAT: Process all parallel teachers (new format with multiple parallels)
                if par_teachers and len(par_teachers) > 0:
                    for i, pt_new in enumerate(par_teachers):
                        ps_new = par_subjects[i] if i < len(par_subjects) else ""
                        if pt_new and pt_new not in ("—", "?"):
                            tg.setdefault(pt_new, [[None]*ppd for _ in range(len(days))])
                            tg[pt_new][d][p] = {"class": cn, "subject": ps_new, "is_ct": False}
                
                # OLD FORMAT: Single parallel teacher (backward compatibility)
                if pt and pt not in ("—", "?"):
                    # Check if this teacher is not already added via new format to avoid duplicates
                    if pt not in par_teachers:
                        tg.setdefault(pt, [[None]*ppd for _ in range(len(days))])
                        tg[pt][d][p] = {"class": cn, "subject": ps, "is_ct": False}

    tlist = sorted(tg.keys())
    if not tlist: st.info("No teacher data."); return
    sel_t = st.selectbox("Select Teacher", tlist, key=f"{key_prefix}_sel")
    if not sel_t: return
    trows = tg.get(sel_t,[])
    header = ["Day"] + [f"P{p+1}" for p in range(ppd)]
    rows = []
    for d, dname in enumerate(days):
        row = [dname]
        for p in range(ppd):
            cell = trows[d][p] if d<len(trows) else None
            row.append(f"{'★' if cell and cell.get('is_ct') else ''}"
                       f"{cell['class']} / {cell['subject']}" if cell else "FREE")
        rows.append(row)
    st.dataframe(pd.DataFrame(rows, columns=header), use_container_width=True, hide_index=True)


def _render_summary_view(tt):
    log.debug("_render_summary_view")
    tasks=tt.get("tasks",[]); days=tt["days"]; ppd=tt["ppd"]
    half1=tt["half1"]; grid=tt["grid"]; all_classes=tt["all_classes"]
    unplaced = [t for t in tasks if t.get("remaining",0)>0]
    if unplaced:
        st.error(f"**{len(unplaced)} task(s) with unplaced periods:**")
        for t in unplaced:
            st.write(f"  ❌ {'+'.join(t.get('cn_list',[]))} | {t['subject']} | "
                     f"{t['teacher']} — {t['remaining']} unplaced")
    else:
        st.success("✅ All periods placed.")
    st.markdown("**Teacher Free-Period Distribution**")
    all_teachers = sorted({cell.get("teacher","")
                            for cn in all_classes
                            for d_row in grid.get(cn,[])
                            for cell in d_row if cell and cell.get("teacher")})
    for teacher in all_teachers:
        busy = {}
        for cn in all_classes:
            for d, d_row in enumerate(grid.get(cn,[])):
                for p, cell in enumerate(d_row):
                    if cell:
                        # Check primary teacher
                        if cell.get("teacher") == teacher:
                            busy.setdefault(d,set()).add(p)
                        # Check old format parallel teacher
                        if cell.get("par_teach") == teacher:
                            busy.setdefault(d,set()).add(p)
                        # Check new format parallel teachers
                        for pt_par in cell.get("par_teachers", []):
                            if pt_par == teacher:
                                busy.setdefault(d,set()).add(p)
        lines = []
        for d in range(len(days)):
            bd  = busy.get(d,set())
            fh1 = half1 - len([x for x in bd if x<half1])
            fh2 = (ppd-half1) - len([x for x in bd if x>=half1])
            if fh1+fh2 == ppd: continue
            lines.append((days[d], fh1, fh2, fh1>=1 and fh2>=1))
        if lines:
            with st.expander(f"**{teacher}**", expanded=False):
                for dname,fh1,fh2,ok in lines:
                    st.write(f"  {'✓' if ok else '⚠'} {dname} — free H1:{fh1}  H2:{fh2}")
    st.divider()
    st.caption("★=CT  ⊕=Combined  ∥=Parallel  ⊕∥=Combined+Parallel")


# ═════════════════════════════════════════════════════════════════════════════
#  SIDEBAR
# ═════════════════════════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown("## 🗓 Timetable Generator")
    st.caption("V4.1 — Streamlit Edition")
    st.divider()

    cur     = st.session_state.page
    s1v     = st.session_state.get("s1_validated", False)
    s2v     = st.session_state.get("s2_validated", False)
    s3v     = st.session_state.get("s3_validated", False)
    gen_done = st.session_state.get("gen_result") is not None

    n_done = sum([s1v, s2v, s3v, gen_done])
    st.progress(n_done / 4, text=f"{n_done} of 4 steps complete")
    st.divider()

    steps = [
        ("step1",           "1️⃣  Basic Config",      True),
        ("step2",           "2️⃣  Class Assignments", s1v),
        ("step3",           "3️⃣  Teacher Settings",  s2v),
        ("generate",        "4️⃣  Generate",          s3v),
        ("final_timetable", "🏁  Final Timetable",    gen_done),
    ]

    for pid, plabel, unlocked in steps:
        active   = (pid == cur)
        locked   = not unlocked and not active
        done_icon = "✅ " if unlocked and not active and pid != "final_timetable" else ""
        lock_icon = "🔒 " if locked else ""
        arrow     = "▶ " if active else ""
        label     = arrow + done_icon + lock_icon + plabel
        if st.button(label, key=f"nav_{pid}",
                     use_container_width=True,
                     disabled=active or locked):
            _nav(pid)

    st.divider()
    _eng_sb = _get_eng()
    if _eng_sb.configuration:
        cfg = _eng_sb.configuration
        st.caption(f"**Config:** {cfg.get('working_days','?')}d × {cfg.get('periods_per_day','?')}p")
        st.caption(f"**Teachers:** {len(cfg.get('teacher_names',[]))}")
        st.caption(f"**Classes:** {sum(cfg.get('classes',{}).values())}")

    st.divider()
    with st.expander("🪵 Debug Log", expanded=False):
        st.caption("Shows last 200 log lines. Format: [LEVEL] file:func:line — msg")
        if st.button("Clear", key="clear_log"):
            _mem_handler.lines.clear(); st.rerun()
        log_text = "\n".join(_mem_handler.lines[-200:])
        st.code(log_text if log_text else "(no entries yet)", language="")


# ═════════════════════════════════════════════════════════════════════════════
#  ROUTER
# ═════════════════════════════════════════════════════════════════════════════
PAGES = {
    "step1":           page_step1,
    "step2":           page_step2,
    "step3":           page_step3,
    "generate":        page_generate,
    "final_timetable": page_final_timetable,
    # Power-user / manual flow pages
    "step4":           page_step4,
    "task_analysis":   page_task_analysis,
    "task_analysis2":  page_task_analysis2,
    "stage2_page":     page_stage2,
}

log.debug("Router: page=%s", st.session_state.page)
PAGES.get(st.session_state.page, page_step1)()


# ─────────────────────────────────────────────────────────────────────────────
#  FOOTER
# ─────────────────────────────────────────────────────────────────────────────
st.markdown(
    """
    <style>
    .dev-footer {
        position: fixed;
        bottom: 0;
        left: 0;
        width: 100%;
        text-align: center;
        padding: 6px 0 6px 0;
        font-size: 0.78rem;
        color: #888888;
        background: rgba(255,255,255,0.85);
        backdrop-filter: blur(4px);
        border-top: 1px solid #e0e0e0;
        z-index: 9999;
        letter-spacing: 0.01em;
    }
    </style>
    <div class="dev-footer">
        Developed by: <strong>Kanika Tanwar</strong>, TGT CS
    </div>
    """,
    unsafe_allow_html=True,
)
