import threading
import uuid
from datetime import date, datetime, UTC

from flask import Flask, render_template, request, redirect, url_for, jsonify

from . import airports, db, scanner

app = Flask(__name__)
app.jinja_env.filters["duration"] = scanner.format_duration

JOBS = {}
JOBS_LOCK = threading.Lock()


def _new_job(total):
    job_id = uuid.uuid4().hex[:12]
    JOBS[job_id] = {
        "status": "running",
        "done": 0,
        "total": total,
        "results": [],
        "started_at": datetime.now(UTC).isoformat(),
    }
    return job_id


def _run_job_in_background(job_id, combos, search_label):
    def progress(done, total, latest_result):
        with JOBS_LOCK:
            JOBS[job_id]["done"] = done
            JOBS[job_id]["total"] = total
            JOBS[job_id]["results"].append(latest_result)

    try:
        scanner.run_scan(combos, search_label, progress_callback=progress)
        with JOBS_LOCK:
            JOBS[job_id]["status"] = "done"
    except Exception as e:
        with JOBS_LOCK:
            JOBS[job_id]["status"] = "error"
            JOBS[job_id]["error"] = str(e)


@app.route("/")
def index():
    return render_template("search.html", groups=airports.GROUPS, weekdays=airports.WEEKDAYS)


@app.route("/search/range", methods=["POST"])
def search_range():
    form = request.form
    origin_group = form["origin_group"]
    destination_group = airports.other_group(origin_group)

    origins = form.getlist(f"{origin_group}_airports") or list(airports.GROUPS[origin_group]["airports"].keys())
    destinations = form.getlist(f"{destination_group}_airports") or list(airports.GROUPS[destination_group]["airports"].keys())

    depart_weekday = int(form["depart_weekday"])
    return_weekday = int(form["return_weekday"])
    months_ahead = int(form["months_ahead"])
    include_near = form.get("include_near") == "on"

    combos = scanner.build_range_combos(
        origins, destinations, depart_weekday, return_weekday, months_ahead, include_near
    )

    depart_name = dict(airports.WEEKDAYS)[depart_weekday]
    return_name = dict(airports.WEEKDAYS)[return_weekday]
    search_label = f"{depart_name} -> {return_name} (next {months_ahead}mo)"

    job_id = _new_job(len(combos))
    thread = threading.Thread(target=_run_job_in_background, args=(job_id, combos, search_label), daemon=True)
    thread.start()

    return redirect(url_for("job_page", job_id=job_id))


@app.route("/search/dates", methods=["POST"])
def search_dates():
    form = request.form
    origin_group = form["origin_group"]
    destination_group = airports.other_group(origin_group)

    origins = form.getlist(f"{origin_group}_airports") or list(airports.GROUPS[origin_group]["airports"].keys())
    destinations = form.getlist(f"{destination_group}_airports") or list(airports.GROUPS[destination_group]["airports"].keys())

    depart_dates = [d for d in form.getlist("depart_date") if d]
    return_dates = [d for d in form.getlist("return_date") if d]

    date_pairs = []
    for depart_str, return_str in zip(depart_dates, return_dates):
        if not depart_str or not return_str:
            continue
        date_pairs.append((
            date.fromisoformat(depart_str),
            date.fromisoformat(return_str),
        ))

    if not date_pairs:
        return redirect(url_for("index"))

    combos = scanner.build_specific_date_combos(origins, destinations, date_pairs)
    job_id = _new_job(len(combos))
    thread = threading.Thread(
        target=_run_job_in_background, args=(job_id, combos, "custom dates"), daemon=True
    )
    thread.start()

    return redirect(url_for("job_page", job_id=job_id))


@app.route("/jobs/<job_id>")
def job_page(job_id):
    if job_id not in JOBS:
        return redirect(url_for("index"))
    return render_template("job.html", job_id=job_id)


@app.route("/api/jobs/<job_id>")
def job_status(job_id):
    job = JOBS.get(job_id)
    if not job:
        return jsonify({"status": "not_found"}), 404
    with JOBS_LOCK:
        results = sorted(
            [r for r in job["results"] if r["price"] is not None],
            key=lambda r: r["price"],
        )
        payload = {
            "status": job["status"],
            "done": job["done"],
            "total": job["total"],
            "results": results,
            "error": job.get("error"),
        }
    return jsonify(payload)


@app.route("/deals")
def deals():
    origin_group = request.args.get("origin_group", "")
    origin_codes = list(airports.GROUPS[origin_group]["airports"].keys()) if origin_group else None
    rows = db.best_deals(limit=150, origin_codes=origin_codes)
    return render_template("deals.html", deals=rows, groups=airports.GROUPS, origin_group=origin_group)


if __name__ == "__main__":
    app.run(debug=True, port=5050)
