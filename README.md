# Seedbench

Seedbench checks calibrated photographs of dry seed lots on a dark matte tray. Use it to screen an image before hand sorting or recording a sample. Load the synthetic pilot tray to see the views with a calibrated example.

## Run

`./start.sh` builds the service with the pinned Python dependencies and starts it at http://127.0.0.1:19884/. Docker Compose is required. Set `SEEDBENCH_PORT` before launch to use a different local port. `docker compose down` stops the service and leaves the named volume. For a separate desk use a different Compose project name and port.

## Inspect a tray

1. Add a single PNG, JPEG or WebP photo, or open **Photo preparation** to prepare a source image. Select **送往种盘** to use a current preparation result in the desk.
2. Draw the inspection rectangle inside the edges of the tray. Use **Mark ruler** to drag between two marks on the same plane as the seeds. Enter the known length in millimeters.
3. Set the brightness floor to separate the seeds from a matte background. Set the minimum projected area to label small flecks. Apply the settings and inspect **Visible count** for complete outlines and partial objects.
4. **Screen widths** compares each grain's projected narrow width with the current opening. **Blue coating** estimates the blue coverage on each complete grain. **Foreign material** locates pale or elongated pieces. **Pale surface marks** highlights bright spots inside grain contours. **Tray density** compares the number of grain centers per observed area across a 3 × 3 grid and can place two square counting windows for a two-quadrat density sample.
5. In **Tray density**, enter the physical side of your quadrat and choose **Suggest two windows**. The app searches non-overlapping square placements whose combined density stays close to the whole-tray density and, within that tolerance, maximizes the distance between the two window centers. Adopt the suggestion to read each window's effective (photo-supported) area, complete grain count and density. Black tray background counts as observed empty area; unsupported photo pixels do not. Grains cut by a window edge, or already partial from missing support, are marked for review and excluded from the count.
6. Click an object number to locate it on the photo. **Original** toggles the marks. **Save check** retains the readings, including the adopted windows, at the current settings. Open a saved check to download its CSV and marked PNG; the windows and their readings reopen exactly as saved.

## Input and approximation

Use a perpendicular photograph of a single layer of separated grain. Each connected foreground region is measured as a projected object. A partial object touches the inspection boundary or missing image support. Width comes from the narrower side of its rotated minimum-area rectangle. Coating and pale marks are visible color cues. Use physical sieves and hand inspection for acceptance measurements.

The two counting windows only count grains whose full outline lies inside the square and on supported photo. A grain touching a window edge, or already flagged partial, is listed in the saved check with its reason (`edge` or `partial`) and is never included in the window count. Window density divides the complete grain count by the supported pixel area converted through the ruler calibration, so black background is sampled as empty tray rather than missing data.

Each photo can be up to 20 MiB, 9 megapixels and 4,000 pixels on one side. Each check accepts 600 visible regions. One library holds up to 24 trays and 30 saved checks per tray. The demo is reproducibly generated for inspection and includes a reference rule, a clipped grain, blue coated grains, pale surface marks and chaff.

## Code

`seedbench/` contains intake, calibrated segmentation, interpretation, storage and exports. `image_lab/` supplies the connected preparation workspace, including color correction, alignment, multi-frame processing and result management. `static/` and `templates/` are served locally. Run `python3 scripts/count_backend.py --project-root . --source-root image_lab --source-root seedbench` to reproduce the backend inventory.
