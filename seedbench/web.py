"""Photo intake, tray editing, direct review and immutable downloads."""

from io import BytesIO
from pathlib import Path

from flask import Blueprint, Response, jsonify, render_template, request, send_file
from PIL import Image

from image_lab.validation import Invalid

from . import demo, inspection, model, output, photo
from .store import Library


def payload():
    return model.document(request.get_json(silent=True))


def make_result(library, tray, mode, settings):
    with Image.open(library.blob(tray["blob"])) as asset:
        view = photo.observe(asset.convert("RGBA"), settings)
    return inspection.report(view, mode, settings)


def install(app, root):
    library = Library(root)
    api = Blueprint("seedbench", __name__, url_prefix="/seed")

    @app.get("/")
    def desk():
        return render_template("seed.html")

    @api.get("/health")
    def health():
        return jsonify(status="ready", service="seedbench")

    @api.get("/config")
    def config():
        return jsonify(settings=model.DEFAULTS, modes=model.MODES)

    @api.get("/trays")
    def trays():
        return jsonify(library.list())

    @api.post("/demo")
    def sample():
        return jsonify(demo.create(library)), 201

    @api.post("/trays")
    def upload():
        file = request.files.get("file")
        if file is None:
            raise Invalid("Choose a tray photo.")
        filename = model.filename(file.filename)
        title = model.name(request.form.get("title") or Path(filename).stem)
        image = photo.decode(file.stream.read(model.MAX_UPLOAD + 1))
        return jsonify(library.create(title, filename, photo.png(image), *image.size, model.DEFAULTS)), 201

    @api.post("/prepare")
    def prepared():
        value = payload()
        project_id = model.name(value.get("project"), "preparation project ID")
        result_id = model.name(value.get("result"), "preparation result ID")
        results = app.extensions["results"]
        meta = results.metadata(project_id, result_id)
        if meta["stale"]:
            raise Invalid("Recompute the preparation result before importing it.")
        result_path = results.image_path(project_id, "image", result_id)
        if isinstance(result_path, bytes):
            source_bytes = result_path
        else:
            with result_path.open("rb") as handle:
                source_bytes = handle.read(model.MAX_UPLOAD + 1)
        image = photo.decode(source_bytes)
        title = model.name(meta.get("name") or "Prepared tray")
        record = library.create(title, title+".png", photo.png(image), *image.size, model.DEFAULTS,
                                preparation={"project": project_id, "result": result_id})
        return jsonify(record), 201

    @api.get("/trays/<tray_id>")
    def detail(tray_id):
        return jsonify(library.tray(tray_id))

    @api.put("/trays/<tray_id>/settings")
    def settings(tray_id):
        value = payload()
        tray = library.tray(tray_id)
        options = model.settings(value.get("settings"), tray["settings"])
        return jsonify(library.update(tray_id, value.get("revision"), options))

    @api.delete("/trays/<tray_id>")
    def remove(tray_id):
        library.remove(tray_id, payload().get("revision"))
        return Response(status=204)

    @api.get("/trays/<tray_id>/image")
    def source(tray_id):
        return send_file(library.blob(library.tray(tray_id)["blob"]), mimetype="image/png", conditional=True)

    @api.post("/trays/<tray_id>/preview")
    def preview(tray_id):
        value = payload()
        tray = library.tray(tray_id)
        options = model.settings(value.get("settings", {}), tray["settings"])
        return jsonify(make_result(library, tray, model.mode(value.get("mode")), options))

    @api.post("/trays/<tray_id>/proofs")
    def retain(tray_id):
        value = payload()
        tray = library.tray(tray_id)
        revision = value.get("revision")
        library.revision(tray, revision)
        mode = model.mode(value.get("mode"))
        result = make_result(library, tray, mode, model.settings(tray["settings"]))
        current, saved = library.retain(tray_id, revision, result)
        return jsonify(tray=current, proof=saved), 201

    @api.get("/trays/<tray_id>/proofs/<proof_id>")
    def reopen(tray_id, proof_id):
        return jsonify(library.proof(tray_id, proof_id))

    @api.get("/trays/<tray_id>/proofs/<proof_id>/report.csv")
    def report(tray_id, proof_id):
        result = library.proof(tray_id, proof_id)
        return Response(output.csv_text(result), mimetype="text/csv",
                        headers={"Content-Disposition": f'attachment; filename="seed-{result["mode"]}.csv"'})

    @api.get("/trays/<tray_id>/proofs/<proof_id>/overlay.png")
    def marked(tray_id, proof_id):
        result = library.proof(tray_id, proof_id)
        with Image.open(library.blob(result["source"])) as image:
            marked_image = output.overlay(image.convert("RGBA"), result)
        return send_file(BytesIO(photo.png(marked_image)), mimetype="image/png",
                         download_name=f'seed-{result["mode"]}.png', as_attachment=True, max_age=0)

    app.register_blueprint(api)
