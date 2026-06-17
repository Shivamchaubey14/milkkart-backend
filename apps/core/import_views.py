"""Admin bulk-import endpoints: upload a spreadsheet (async, non-blocking),
poll progress, list recent imports, and download per-kind templates.
"""

from django.http import HttpResponse
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from .import_service import ParseError, TEMPLATES, parse_spreadsheet, start_import, template_bytes
from .models import BulkImport
from .permissions import IsOpsManager

MAX_UPLOAD_BYTES = 5 * 1024 * 1024  # 5 MB


def _serialize(job):
    return {
        "id": job.id,
        "kind": job.kind,
        "status": job.status,
        "filename": job.filename,
        "total_rows": job.total_rows,
        "processed_rows": job.processed_rows,
        "success_count": job.success_count,
        "error_count": job.error_count,
        "progress_percent": job.progress_percent,
        "errors": job.errors,
        "message": job.message,
        "created_at": job.created_at,
    }


@api_view(["GET", "POST"])
@permission_classes([IsOpsManager])
def imports(request):
    if request.method == "GET":
        jobs = BulkImport.objects.all()[:20]
        return Response([_serialize(j) for j in jobs])

    kind = (request.data.get("kind") or "").strip()
    if kind not in BulkImport.Kind.values:
        return Response({"error": "Choose a valid import type."}, status=status.HTTP_400_BAD_REQUEST)

    upload = request.FILES.get("file")
    if not upload:
        return Response({"error": "Attach a .xlsx or .csv file."}, status=status.HTTP_400_BAD_REQUEST)
    if upload.size > MAX_UPLOAD_BYTES:
        return Response({"error": "File too large (max 5 MB)."}, status=status.HTTP_400_BAD_REQUEST)

    try:
        rows = parse_spreadsheet(upload)
    except ParseError as exc:
        return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    if not rows:
        return Response({"error": "No data rows found in the file."}, status=status.HTTP_400_BAD_REQUEST)

    job = BulkImport.objects.create(
        kind=kind, filename=upload.name[:255], total_rows=len(rows), created_by=request.user
    )
    start_import(job.id, rows)  # non-blocking: processes in a background thread
    return Response(_serialize(job), status=status.HTTP_201_CREATED)


@api_view(["GET"])
@permission_classes([IsOpsManager])
def import_detail(request, import_id):
    try:
        job = BulkImport.objects.get(pk=import_id)
    except BulkImport.DoesNotExist:
        return Response({"error": "Import not found."}, status=status.HTTP_404_NOT_FOUND)
    return Response(_serialize(job))


@api_view(["GET"])
@permission_classes([IsOpsManager])
def import_template(request, kind):
    if kind not in TEMPLATES:
        return Response({"error": "Unknown template."}, status=status.HTTP_404_NOT_FOUND)
    content = template_bytes(kind)
    resp = HttpResponse(
        content, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    resp["Content-Disposition"] = f'attachment; filename="milkkart-{kind}-template.xlsx"'
    return resp
