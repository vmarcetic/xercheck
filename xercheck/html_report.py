"""Server-rendered HTML report. Schedule text is escaped before it is inserted.

Layout: a left sidebar (Overview, Schedule checks, Findings, Methodology), an
overview with one panel of headline numbers per file, one chart, a written
brief, plain-English cards for every check, and the findings table. All of it
is built from the checker's own output. Nothing here changes a rule.
"""

from html import escape

from xercheck.chart import findings_chart
from xercheck.check import ALL_CODES, CODE_LABELS, DEFAULT_HIGH_FLOAT_HOURS, Report, SourceInfo, filter_findings, format_hours
from xercheck.explain import SCHEDULE_CODES, advice, high_float_rule, meaning
from xercheck.overview import DATA_DATE_FIELD, FINISH_FIELD

_PAGE_STYLE = """
:root { --ink: #0a0a0a; --muted: #6b7280; --soft: #9ca3af; --line: #e5e7eb;
  --panel: #f9fafb; --blue: #2563eb; --amber: #b45309; --amber-bg: #fffbeb;
  --green: #15803d; --green-bg: #f0fdf4; --red: #b91c1c; --red-bg: #fef2f2; }
* { box-sizing: border-box; }
body { margin: 0; color: var(--ink); background: #fff;
  font-family: system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
  font-size: 14px; line-height: 1.5; -webkit-font-smoothing: antialiased; }
a { color: inherit; }
code, .mono { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 0.86em; }
.topbar { height: 60px; display: flex; align-items: center; justify-content: space-between;
  padding: 0 24px; border-bottom: 1px solid var(--line); }
.brand { display: flex; align-items: center; gap: 10px; font-weight: 600; font-size: 15px; }
.brand-mark { width: 28px; height: 28px; border-radius: 7px; background: var(--ink); color: #fff;
  display: grid; place-items: center; font-size: 11px; font-weight: 700; letter-spacing: 0.02em; }
.badge-local { font-size: 11px; font-weight: 600; letter-spacing: 0.08em; text-transform: uppercase; }
.badge-local::before { content: ""; display: inline-block; width: 6px; height: 6px; border-radius: 50%;
  background: var(--green); margin-right: 7px; vertical-align: middle; }
.layout { display: grid; grid-template-columns: 220px minmax(0, 1fr); min-height: calc(100vh - 60px); }
.sidebar { border-right: 1px solid var(--line); padding: 24px 16px; position: sticky; top: 0;
  align-self: start; height: calc(100vh - 60px); display: flex; flex-direction: column; gap: 20px; }
.eyebrow { font-size: 10.5px; font-weight: 600; letter-spacing: 0.12em; text-transform: uppercase; color: var(--muted); }
.sidebar nav { display: flex; flex-direction: column; gap: 2px; margin-top: 10px; }
.sidebar nav a { text-decoration: none; padding: 8px 10px; border-radius: 8px; color: #374151; font-size: 13px; }
.sidebar nav a:hover, .sidebar nav a.active { background: #f3f4f6; color: var(--ink); font-weight: 500; }
.side-note { border-top: 1px solid var(--line); padding-top: 16px; font-size: 12px; color: #4b5563; }
.side-note strong { display: block; color: var(--ink); margin-bottom: 4px; font-size: 12px; }
.side-note p { margin: 0 0 8px; }
main { padding: 20px 40px 64px; max-width: 1180px; width: 100%; }
.crumbs { font-size: 12px; color: var(--muted); margin-bottom: 24px; }
.crumbs span { margin: 0 6px; color: var(--soft); }
.hero { display: flex; justify-content: space-between; align-items: flex-start; gap: 24px; margin-bottom: 24px; }
h1 { font-size: 30px; line-height: 1.15; letter-spacing: -0.02em; margin: 8px 0 10px; font-weight: 700; }
.lede { margin: 0; color: #4b5563; font-size: 13.5px; max-width: 680px; }
.btn { display: inline-flex; align-items: center; gap: 8px; background: var(--ink); color: #fff;
  border: 0; border-radius: 9px; padding: 10px 16px; font: inherit; font-weight: 600; font-size: 13px;
  text-decoration: none; cursor: pointer; white-space: nowrap; }
.btn:hover { background: #262626; }
.file-panel { border: 1px solid var(--line); border-radius: 12px; margin-bottom: 20px; overflow: hidden; }
.file-id { display: flex; align-items: center; gap: 14px; background: var(--panel); padding: 14px 18px;
  border-bottom: 1px solid var(--line); flex-wrap: wrap; }
.file-icon { width: 34px; height: 34px; border: 1px solid var(--line); border-radius: 8px; background: #fff;
  display: grid; place-items: center; font-size: 10px; font-weight: 700; color: var(--muted); }
.file-name { font-weight: 600; font-size: 14px; word-break: break-all; }
.file-sub { font-size: 12px; color: var(--muted); }
.file-date { margin-left: auto; text-align: right; }
.file-date .val { font-size: 14px; font-weight: 500; }
.kpis { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); }
.kpi { padding: 16px 18px; border-right: 1px solid var(--line); }
.kpi:last-child { border-right: 0; }
.kpi .num { font-size: 26px; font-weight: 500; letter-spacing: -0.01em; margin: 6px 0 2px; }
.kpi .num small { font-size: 15px; color: #4b5563; margin-left: 4px; }
.kpi .num.na { font-size: 16px; color: var(--muted); font-weight: 500; padding-top: 8px; }
.kpi .hint { font-size: 11.5px; color: var(--muted); }
.grid2 { display: grid; grid-template-columns: minmax(0, 1.45fr) minmax(0, 1fr); gap: 20px; margin: 8px 0 36px; }
.card { border: 1px solid var(--line); border-radius: 12px; padding: 18px 20px; background: #fff; }
.card.tinted { background: var(--panel); }
.card-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; margin-bottom: 10px; }
h2 { font-size: 16px; margin: 4px 0 0; font-weight: 650; letter-spacing: -0.01em; }
h3 { font-size: 14px; margin: 0; font-weight: 600; }
.pill { display: inline-block; border: 1px solid var(--line); border-radius: 999px; padding: 2px 9px;
  font-size: 11px; color: #4b5563; background: #fff; white-space: nowrap; }
.pill.ok { color: var(--green); background: var(--green-bg); border-color: #bbf7d0; }
.pill.warn { color: var(--amber); background: var(--amber-bg); border-color: #fde68a; }
.pill.bad { color: var(--red); background: var(--red-bg); border-color: #fecaca; }
.card-note { font-size: 12px; color: var(--muted); margin: 0 0 8px; }
details { font-size: 12px; color: #4b5563; margin-top: 10px; }
summary { cursor: pointer; }
.brief { list-style: none; margin: 0; padding: 0; }
.brief li { padding: 11px 0; border-bottom: 1px solid var(--line); font-size: 13px; }
.brief li:last-child { border-bottom: 0; }
.brief .tag { display: block; margin-top: 3px; color: var(--muted); font-family: ui-monospace, Menlo, Consolas, monospace; font-size: 11px; }
section { scroll-margin-top: 16px; }
.section-head { margin: 8px 0 14px; }
.section-head p { margin: 4px 0 0; color: #4b5563; font-size: 13px; max-width: 760px; }
.checks { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; margin-bottom: 18px; }
.check { border: 1px solid var(--line); border-radius: 12px; padding: 16px 18px; scroll-margin-top: 16px; }
.check .top { display: flex; justify-content: space-between; align-items: center; gap: 10px; margin-bottom: 6px; }
.check p { margin: 6px 0 0; font-size: 13px; }
.check .look { color: #4b5563; }
.check .code { color: var(--soft); font-size: 11px; }
.quiet { border: 1px solid var(--line); border-radius: 12px; overflow: hidden; margin-bottom: 36px; }
.quiet-row { display: grid; grid-template-columns: 180px minmax(0, 1fr) 90px; gap: 14px; padding: 11px 16px;
  border-bottom: 1px solid var(--line); font-size: 12.5px; align-items: start; scroll-margin-top: 16px; }
.quiet-row:last-child { border-bottom: 0; }
.quiet-row .look { color: var(--muted); }
.quiet-row .count { text-align: right; }
.toolbar { display: flex; align-items: center; gap: 12px; margin-bottom: 10px; font-size: 13px; }
select, input[type="text"] { font: inherit; padding: 7px 10px; border: 1px solid #d1d5db; border-radius: 8px; background: #fff; }
.wrap { overflow-x: auto; border: 1px solid var(--line); border-radius: 12px; margin-bottom: 36px; }
table { width: 100%; border-collapse: collapse; font-size: 12.5px; }
caption { text-align: left; padding: 10px 14px; color: var(--muted); font-size: 12px; }
th, td { text-align: left; vertical-align: top; padding: 9px 12px; border-top: 1px solid var(--line); }
th { background: var(--panel); font-weight: 600; font-size: 11px; letter-spacing: 0.04em; text-transform: uppercase; color: #4b5563; }
td .code { display: block; color: var(--soft); font-size: 10.5px; }
td a { text-decoration: none; font-weight: 500; }
td a:hover { text-decoration: underline; }
.method { columns: 2; column-gap: 32px; font-size: 13px; color: #374151; }
.method p { margin: 0 0 12px; break-inside: avoid; }
.fineprint { font-size: 12px; color: var(--muted); border-top: 1px solid var(--line); padding-top: 14px; margin-top: 8px; }
.upload { border: 1px solid var(--line); border-radius: 12px; overflow: hidden; margin-bottom: 36px; }
.upload .body { padding: 20px; display: grid; grid-template-columns: minmax(0, 1fr) 220px; gap: 20px; }
.upload label { display: block; font-weight: 600; font-size: 13px; margin-bottom: 6px; }
.upload .help { font-size: 12px; color: var(--muted); margin: 6px 0 0; }
.upload .foot { background: var(--panel); border-top: 1px solid var(--line); padding: 12px 20px;
  display: flex; justify-content: space-between; align-items: center; gap: 12px; font-size: 12px; color: var(--muted); }
input[type="file"] { font: inherit; width: 100%; padding: 18px; border: 1px dashed #cbd5e1; border-radius: 10px; background: var(--panel); }
@media (max-width: 900px) {
  .layout { grid-template-columns: 1fr; }
  .sidebar { position: static; height: auto; border-right: 0; border-bottom: 1px solid var(--line); }
  main { padding: 20px; }
  .kpis { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .grid2, .checks, .upload .body { grid-template-columns: 1fr; }
  .method { columns: 1; }
  .quiet-row { grid-template-columns: 1fr; }
}
"""

_FILTER_SCRIPT = """
<script>
(function () {
  var select = document.getElementById("only");
  var rows = document.querySelectorAll("tr[data-code]");
  var out = document.getElementById("shown-count");
  if (!select || !out) return;
  function apply() {
    var want = select.value;
    var shown = 0;
    for (var i = 0; i < rows.length; i++) {
      var keep = !want || rows[i].getAttribute("data-code") === want;
      rows[i].hidden = !keep;
      if (keep) shown += 1;
    }
    out.textContent = shown + " shown";
  }
  select.addEventListener("change", apply);
  var jumps = document.querySelectorAll("a[data-filter]");
  for (var j = 0; j < jumps.length; j++) {
    jumps[j].addEventListener("click", function () {
      select.value = this.getAttribute("data-filter");
      apply();
    });
  }
})();
</script>
"""

_METHOD = """
<section id="methodology">
  <div class="section-head">
    <div class="eyebrow">Methodology</div>
    <h2>How the checker reads a P6 export</h2>
    <p>Plain-English version of <code>EXPLAIN.md</code>. The checker reads the file. It does not run a schedule.</p>
  </div>
  <div class="method">
    <p><strong>What an XER is.</strong> A P6 export is a tab-separated text file. Each table starts with <code>%T</code>, its columns are listed on <code>%F</code>, and every <code>%R</code> line is one row. The checker matches values to columns by name.</p>
    <p><strong>What it reads.</strong> Only <code>PROJECT</code>, <code>TASK</code> (activities) and <code>TASKPRED</code> (relationships). Other tables, such as calendars or resources, are listed as “not used by these checks”. That is not an error.</p>
    <p><strong>Missing links.</strong> Every activity needs at least one predecessor and one successor. A start milestone (<code>TT_Mile</code>) may have no predecessor. A finish milestone (<code>TT_FinMile</code>) may have no successor. Nothing else is exempt, including level-of-effort and WBS summary activities.</p>
    <p><strong>Links stay inside one file.</strong> A relationship counts only when both activities are in the same file. If the other project is not in the file, the link is “unknown scope”: it is not called missing, and it is not assumed to be a real external tie.</p>
    <p><strong>Float is what P6 exported.</strong> Total float comes from <code>total_float_hr_cnt</code>, in working hours. The checker does not recalculate it and does not convert hours to days. Below 0 is negative float. Above the threshold (default 160 working hours) is high float. Blank or unreadable float is reported, never treated as 0.</p>
    <p><strong>Overview numbers.</strong> Exported finish is <code>PROJECT.scd_end_date</code>. Data date is <code>PROJECT.last_recalc_date</code>. Zero/negative float and median total float use the same stored float column as the checks. If a field is missing, the page says so instead of showing a date.</p>
  </div>
</section>
"""


def _shell(title: str, main_html: str, *, active: str = "overview", include_filter_script: bool) -> str:
    links = [
        ("overview", "#overview", "Overview"),
        ("checks", "#checks", "Schedule checks"),
        ("findings", "#findings", "Findings"),
        ("methodology", "#methodology", "Methodology"),
    ]
    nav = "".join(
        f'<a href="{href}"{" class=\"active\"" if key == active else ""}>{label}</a>'
        for key, href, label in links
    )
    body = f"""
<header class="topbar">
  <div class="brand"><span class="brand-mark" aria-hidden="true">XER</span>XER checker</div>
  <div class="badge-local" title="Files are checked in this process and are not sent anywhere.">Local</div>
</header>
<div class="layout">
  <aside class="sidebar">
    <div>
      <div class="eyebrow">Review workspace</div>
      <nav aria-label="Sections">{nav}</nav>
    </div>
    <div class="side-note">
      <strong>Runs on this computer</strong>
      <p>Files are checked in this process. Nothing is stored or sent to another service.</p>
      <p>Review aid, not a P6 replacement.</p>
    </div>
  </aside>
  <main>
{main_html}
  </main>
</div>
"""
    return _page(title, body, include_filter_script=include_filter_script)


def _check_reference() -> str:
    """Static list of what every check means, for the upload page."""
    cards = []
    for code in SCHEDULE_CODES:
        extra = ""
        if code == "high_float":
            default = DEFAULT_HIGH_FLOAT_HOURS
            extra = f"<p>{escape(high_float_rule(default, format_hours(default)))}</p>"
        cards.append(
            f'<div class="check"><div class="top"><h3>{escape(CODE_LABELS[code])}</h3>'
            f'<span class="code mono">{escape(code)}</span></div>'
            f"<p>{escape(meaning(code))}</p>{extra}<p class=\"look\">{escape(advice(code))}</p></div>"
        )
    rows = []
    for code in ALL_CODES:
        if code in SCHEDULE_CODES:
            continue
        rows.append(
            f'<div class="quiet-row"><div><strong>{escape(CODE_LABELS[code])}</strong>'
            f'<div class="code mono">{escape(code)}</div></div>'
            f"<div>{escape(meaning(code))} <span class=\"look\">{escape(advice(code))}</span></div><div></div></div>"
        )
    return (
        '<section id="checks"><div class="section-head"><div class="eyebrow">Schedule checks</div>'
        "<h2>What each check looks for</h2><p>The first four are about schedule logic and float. "
        "The rest say whether the file itself could be read cleanly.</p></div>"
        f'<div class="checks">{"".join(cards)}</div><div class="quiet">{"".join(rows)}</div></section>'
    )


def render_form() -> str:
    main_html = f"""
<div class="crumbs">Workspace<span>›</span>Schedule review</div>
<section id="overview">
<div class="hero"><div>
  <div class="eyebrow">Exported schedule check</div>
  <h1>Review the exported schedule.</h1>
  <p class="lede">Choose one or more Primavera P6 <code>.xer</code> exports. Every finding comes from the exported data: missing logic, negative float, high float, and rows that could not be read.</p>
</div></div>
<form class="upload" method="post" action="/" enctype="multipart/form-data">
  <div class="body">
    <div>
      <label for="xer">XER files</label>
      <input id="xer" name="xer" type="file" accept=".xer,text/plain" multiple required>
      <p class="help">Up to 6 files, 2 MB each. Each file is checked on its own; ids are never matched across files.</p>
    </div>
    <div>
      <label for="high_float_hours">High float, hours</label>
      <input id="high_float_hours" name="high_float_hours" type="text" value="160" inputmode="decimal">
      <p class="help">Working hours from <code>total_float_hr_cnt</code>, not days. 160 h is about four 40-hour weeks. Exactly the threshold is not flagged.</p>
    </div>
  </div>
  <div class="foot"><span>Files stay in this process. Nothing is sent to another service.</span><button class="btn" type="submit">Check files</button></div>
</form>
</section>
{_check_reference()}
{_METHOD}
"""
    return _shell("XER checker", main_html, include_filter_script=False)


def render_message(title: str, message: str, *, status_hint: str = "") -> str:
    hint = f"<p>{escape(status_hint)}</p>" if status_hint else ""
    main_html = (
        '<div class="crumbs">Workspace<span>›</span>Schedule review</div>'
        f'<section id="overview"><div class="eyebrow">Check not run</div><h1>{escape(title)}</h1>'
        f'{hint}<p class="lede">{escape(message)}</p>'
        '<p style="margin-top:20px"><a class="btn" href="/">Back to upload</a></p></section>'
    )
    return _shell(title, main_html, include_filter_script=False)


def _plural(count: int, one: str, many: str) -> str:
    return f"{count} {one if count == 1 else many}"


def _date_parts(text: str) -> tuple[str, str]:
    if " " in text:
        day, clock = text.split(" ", 1)
        return day, clock
    return text, ""


def _file_counts(report: Report, index: int) -> dict[str, int]:
    totals: dict[str, int] = {}
    for finding in report.findings:
        if finding.file_index == index:
            totals[finding.code] = totals.get(finding.code, 0) + 1
    return totals


def _file_panel(report: Report, index: int, source: SourceInfo) -> str:
    ov = source.overview
    projects = ", ".join(source.projects) if source.projects else "No project name in PROJECT"
    sub = (
        f"Project {escape(projects)} · {escape(source.encoding)} · "
        f'sha256 <span class="mono" title="{escape(source.sha256)}">{escape(source.sha256[:12])}…</span>'
    )
    if ov is not None and ov.data_date:
        data_date = (
            f'<div class="val">{escape(ov.data_date)}</div>'
            f'<div class="file-sub">{escape(ov.data_date_note)} · P6 local time</div>'
        )
    else:
        note = ov.data_date_note if ov is not None else "Not available."
        data_date = f'<div class="val">Not in export</div><div class="file-sub">{escape(note)}</div>'
    # Exported finish
    if ov is not None and ov.exported_finish:
        day, clock = _date_parts(ov.exported_finish)
        finish = (
            f'<div class="num">{escape(day)}</div>'
            f'<div class="hint">{escape(clock + " · " if clock else "")}{escape(ov.finish_note)}. '
            "Existing export, not a new forecast.</div>"
        )
    else:
        note = ov.finish_note if ov is not None else "Not available."
        finish = f'<div class="num na">Not in export</div><div class="hint">{escape(note)} No date was invented.</div>'
    activities = (
        f'<div class="num">{source.activity_count}</div>'
        f'<div class="hint">{_plural(source.relationship_count, "relationship", "relationships")} in this file</div>'
    )
    column = source.float_column
    if ov is None or column is None:
        zero = '<div class="num na">Not in export</div><div class="hint">No total-float column in TASK.</div>'
        med = zero
    else:
        excluded = (
            f"; {ov.float_excluded} blank or unreadable left out" if ov.float_excluded else ""
        )
        zero = (
            f'<div class="num">{ov.zero_or_negative}</div>'
            f'<div class="hint">of {ov.float_values} activities with readable float are at or below 0 h '
            f"({ov.negative} below 0){escape(excluded)}</div>"
        )
        if ov.median_float_hours is None:
            med = '<div class="num na">No values</div><div class="hint">No readable float values.</div>'
        else:
            med = (
                f'<div class="num">{escape(format_hours(ov.median_float_hours))}<small>h</small></div>'
                f'<div class="hint">Exported working hours from <code>{escape(column)}</code>, not calendar days</div>'
            )
    return f"""
<div class="file-panel">
  <div class="file-id">
    <div class="file-icon" aria-hidden="true">XER</div>
    <div><div class="file-name">{escape(source.filename)}</div><div class="file-sub">{sub}</div></div>
    <div class="file-date"><div class="eyebrow">Data date</div>{data_date}</div>
  </div>
  <div class="kpis">
    <div class="kpi"><div class="eyebrow">Exported finish</div>{finish}</div>
    <div class="kpi"><div class="eyebrow">Activities</div>{activities}</div>
    <div class="kpi"><div class="eyebrow">Zero / negative float</div>{zero}</div>
    <div class="kpi"><div class="eyebrow">Median total float</div>{med}</div>
  </div>
</div>"""


def _brief_items(report: Report) -> list[tuple[str, str]]:
    items: list[tuple[str, str]] = []
    many = len(report.sources) > 1
    threshold = format_hours(report.threshold_hours)
    for index, source in enumerate(report.sources):
        prefix = f"{source.filename}: " if many else ""
        ov = source.overview
        items.append(
            (
                f"{prefix}The export contains {_plural(source.activity_count, 'activity', 'activities')} "
                f"and {_plural(source.relationship_count, 'relationship', 'relationships')}.",
                "TASK / TASKPRED rows",
            )
        )
        if ov is not None and ov.exported_finish:
            items.append(
                (
                    f"{prefix}The exported finish is {ov.exported_finish} (P6 local time; the file has no time zone).",
                    f"PROJECT.{FINISH_FIELD}",
                )
            )
        else:
            items.append((f"{prefix}The export has no readable scheduled finish date.", f"PROJECT.{FINISH_FIELD}"))
        counts = _file_counts(report, index)
        mp, ms = counts.get("missing_predecessor", 0), counts.get("missing_successor", 0)
        items.append(
            (
                f"{prefix}{_plural(mp, 'activity has', 'activities have')} no predecessor and "
                f"{_plural(ms, 'activity has', 'activities have')} no successor. "
                "Open ends make the critical path and float less reliable.",
                "missing_predecessor · missing_successor",
            )
        )
        neg = counts.get("negative_float", 0)
        items.append(
            (
                f"{prefix}{_plural(neg, 'activity has', 'activities have')} negative exported total float"
                + (", so the project is already past a required finish or constraint." if neg else "."),
                "negative_float",
            )
        )
        high = counts.get("high_float", 0)
        items.append(
            (
                f"{prefix}{_plural(high, 'activity has', 'activities have')} exported total float above "
                f"{threshold} working hours.",
                "high_float",
            )
        )
        broken = sum(
            counts.get(code, 0)
            for code in ("malformed_row", "malformed_link", "dangling_link", "duplicate_activity",
                         "unsupported_directive", "missing_float", "nonnumeric_float", "nonfinite_float")
        )
        if broken:
            items.append(
                (
                    f"{prefix}{_plural(broken, 'row or value needs', 'rows or values need')} a data check "
                    "(broken rows, broken links, duplicates, or blank/unreadable float).",
                    "file and data checks",
                )
            )
        else:
            items.append((f"{prefix}No broken rows, broken links, or unreadable float values.", "file and data checks"))
        unknown = counts.get("unknown_scope", 0)
        if unknown:
            items.append(
                (
                    f"{prefix}{_plural(unknown, 'link points', 'links point')} to a project that is not in this file.",
                    "unknown_scope",
                )
            )
        missing_parts = sum(counts.get(code, 0) for code in ("missing_table", "unsupported_field", "missing_header", "missing_end_marker"))
        if missing_parts:
            items.append(
                (
                    f"{prefix}{_plural(missing_parts, 'part of the file is', 'parts of the file are')} missing, "
                    "so some checks could not run. See the findings for which.",
                    "missing_table · unsupported_field · header/end",
                )
            )
        tables = counts.get("unsupported_table", 0)
        if tables:
            items.append(
                (
                    f"{prefix}{_plural(tables, 'other table was', 'other tables were')} seen and not used by these checks. "
                    "That is normal for a full P6 export.",
                    "unsupported_table",
                )
            )
    return items


def _check_cards(report: Report) -> str:
    counts = report.counts()
    threshold = format_hours(report.threshold_hours)
    cards = []
    for code in SCHEDULE_CODES:
        total = counts.get(code, 0)
        pill_class = "ok" if total == 0 else ("bad" if code == "negative_float" else "warn")
        pill = "Clear" if total == 0 else _plural(total, "finding", "findings")
        extra = ""
        if code == "high_float":
            extra = f"<p>{escape(high_float_rule(report.threshold_hours, threshold))}</p>"
        link = (
            f' <a href="#findings" data-filter="{escape(code)}">See findings ↓</a>' if total else ""
        )
        cards.append(
            f'<div class="check" id="check-{escape(code)}"><div class="top">'
            f'<h3>{escape(CODE_LABELS[code])}</h3><span class="pill {pill_class}">{escape(pill)}</span></div>'
            f'<div class="code mono">{escape(code)}</div>'
            f"<p>{escape(meaning(code))}</p>{extra}<p class=\"look\">{escape(advice(code))}{link}</p></div>"
        )
    rows = []
    for code in ALL_CODES:
        if code in SCHEDULE_CODES:
            continue
        total = counts.get(code, 0)
        if code == "unsupported_table":
            pill = f'<span class="pill">{total} seen</span>' if total else '<span class="pill ok">None</span>'
        else:
            pill = (
                f'<span class="pill warn">{escape(_plural(total, "finding", "findings"))}</span>'
                if total
                else '<span class="pill ok">Clear</span>'
            )
        rows.append(
            f'<div class="quiet-row" id="check-{escape(code)}"><div><strong>{escape(CODE_LABELS[code])}</strong>'
            f'<div class="code mono">{escape(code)}</div></div>'
            f"<div>{escape(meaning(code))} <span class=\"look\">{escape(advice(code))}</span></div>"
            f'<div class="count">{pill}</div></div>'
        )
    return (
        '<section id="checks"><div class="section-head"><div class="eyebrow">03 / Schedule checks</div>'
        "<h2>What was checked, and what it means</h2>"
        "<p>The first four are about schedule logic and float, the things a planner acts on. "
        "The list below them says whether the file itself could be read cleanly.</p></div>"
        f'<div class="checks">{"".join(cards)}</div><div class="quiet">{"".join(rows)}</div></section>'
    )


def render_html(report: Report, *, show_home_link: bool = False) -> str:
    counts = report.counts()
    count_bits = []
    for code in CHART_CODES_WITH_EXTRAS(report):
        count_bits.append(f"{escape(CODE_LABELS.get(code, code))} {counts.get(code, 0)}")
    options = ['<option value="">All findings</option>']
    for code in ALL_CODES:
        options.append(
            f'<option value="{escape(code)}">{escape(CODE_LABELS.get(code, code))}</option>'
        )
    panels = "".join(_file_panel(report, index, source) for index, source in enumerate(report.sources))
    brief = "".join(
        f'<li>{escape(text)}<span class="tag">{escape(tag)}</span></li>' for text, tag in _brief_items(report)
    )
    finding_rows = []
    for finding in report.findings:
        line = "" if finding.line is None else str(finding.line)
        finding_rows.append(
            "<tr data-code=\""
            + escape(finding.code)
            + "\"><td>"
            + escape(finding.filename)
            + "</td><td>"
            + escape(line)
            + "</td><td>"
            + escape(finding.table)
            + '</td><td><a href="#check-'
            + escape(finding.code)
            + '" title="'
            + escape(meaning(finding.code))
            + '">'
            + escape(CODE_LABELS.get(finding.code, finding.code))
            + '</a><span class="code mono">'
            + escape(finding.code)
            + "</span></td><td>"
            + escape(finding.activity_id)
            + "</td><td>"
            + escape(finding.activity_name)
            + "</td><td>"
            + escape(finding.message)
            + "</td></tr>"
        )
    if not finding_rows:
        finding_rows.append(
            '<tr><td colspan="7">No findings. The selected files produced none of the checked conditions.</td></tr>'
        )
    home = '<a class="btn" href="/">↑ Check other files</a>' if show_home_link else ""
    file_word = "P6 export" if len(report.sources) == 1 else f"{len(report.sources)} P6 exports"
    main_html = f"""
<div class="crumbs">Workspace<span>›</span>Schedule review</div>
<section id="overview">
<div class="hero"><div>
  <div class="eyebrow">Exported schedule check</div>
  <h1>Review the exported schedule.</h1>
  <p class="lede">A traceable review of your {escape(file_word)}. Every finding starts with the data in the file, with its table and line.</p>
</div>{home}</div>
{panels}
<div class="grid2">
  <div class="card">
    <div class="card-head"><div><div class="eyebrow">01 / Findings profile</div><h2>Findings by check</h2></div>
      <span class="pill">All files</span></div>
    <p class="card-note">Blue bars are schedule logic and float. Grey bars are file and data checks.</p>
    <div class="chart">{findings_chart(report)}</div>
    <details><summary>Chart values</summary><p>{' · '.join(count_bits)}</p></details>
  </div>
  <div class="card tinted">
    <div class="card-head"><div><div class="eyebrow">02 / Written review</div><h2>Executive brief</h2></div>
      <span class="pill">From checker output</span></div>
    <ul class="brief">{brief}</ul>
  </div>
</div>
</section>
{_check_cards(report)}
<section id="findings">
  <div class="section-head"><div class="eyebrow">04 / Findings</div><h2>Every finding, with its source line</h2>
  <p>High-float threshold: <strong>{escape(format_hours(report.threshold_hours))} hours</strong>. A value equal to the threshold is not high. Empty, non-numeric, and non-finite float is not treated as zero. Click a check name for what it means.</p></div>
  <form class="toolbar" onsubmit="return false">
    <label for="only">Filter</label>
    <select id="only" name="only">{''.join(options)}</select>
    <span id="shown-count">{len(report.findings)} shown</span>
  </form>
  <noscript><p>The filter list runs in the browser. With that script unavailable, the full table stays visible. The command line filter is <code>--only</code>.</p></noscript>
  <div class="wrap">
  <table>
    <caption>Findings by file, with the source line and the reason.</caption>
    <thead><tr><th>File</th><th>Line</th><th>Table</th><th>Check</th><th>Activity</th><th>Name</th><th>What the checker found</th></tr></thead>
    <tbody>{''.join(finding_rows)}</tbody>
  </table>
  </div>
</section>
{_METHOD}
<p class="fineprint">{escape(report.disclaimer)}</p>
"""
    return _shell("XER check", main_html, include_filter_script=True)


def render_text(report: Report, only: str = "") -> str:
    shown = filter_findings(report.findings, only)
    counts = report.counts()
    lines = [
        DISCLAIMER_LINE(report),
        f"High-float threshold: {format_hours(report.threshold_hours)} hours.",
        "",
        "Files:",
    ]
    for source in report.sources:
        column = source.float_column or "not present"
        projects = ", ".join(source.projects) if source.projects else "none named"
        lines.append(
            f"- {source.filename}: {source.activity_count} activities, "
            f"{source.relationship_count} relationships, float column {column}, "
            f"sha256 {source.sha256}, projects {projects}"
        )
        ov = source.overview
        if ov is not None:
            finish = ov.exported_finish or "not in export"
            median = (
                f"{format_hours(ov.median_float_hours)} h"
                if ov.median_float_hours is not None
                else "not available"
            )
            lines.append(
                f"  overview (display only): exported finish {finish} ({FINISH_FIELD}), "
                f"data date {ov.data_date or 'not in export'} ({DATA_DATE_FIELD}), "
                f"zero/negative float {ov.zero_or_negative} of {ov.float_values}, "
                f"median total float {median}"
            )
    lines.append("")
    lines.append("Counts:")
    for code in list(CHART_CODES_WITH_EXTRAS(report)):
        lines.append(f"- {code}: {counts.get(code, 0)}")
    if only:
        lines.append("")
        lines.append(f"Filter: {only}")
    lines.append("")
    if not shown:
        lines.append("No findings for this view.")
    for finding in shown:
        line = "-" if finding.line is None else str(finding.line)
        lines.append(
            f"[{finding.code}] {finding.filename} {finding.table or '-'} line {line} "
            f"{finding.activity_id} {finding.activity_name}".rstrip()
        )
        lines.append(f"    {finding.message}")
    lines.append("")
    return "\n".join(lines)


def CHART_CODES_WITH_EXTRAS(report: Report) -> list[str]:
    from xercheck.check import CHART_CODES

    extras = [code for code in ALL_CODES if code not in CHART_CODES and report.counts().get(code)]
    return list(CHART_CODES) + extras


def DISCLAIMER_LINE(report: Report) -> str:
    return report.disclaimer


def _page(title: str, body: str, *, include_filter_script: bool) -> str:
    script = _FILTER_SCRIPT if include_filter_script else ""
    return (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{escape(title)}</title>\n"
        f"<style>{_PAGE_STYLE}</style>\n"
        "</head>\n"
        "<body>\n"
        f"{body}\n"
        f"{script}\n"
        "</body>\n"
        "</html>\n"
    )
