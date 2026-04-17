from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, UTC
from pathlib import Path
from typing import Any

from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient
from dotenv import load_dotenv


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            'Delete Azure Blob Storage test artifacts by prefix/substring. '
            'Safe by default: dry-run unless --yes is provided.'
        )
    )
    parser.add_argument('--yes', action='store_true', help='Actually delete blobs. Without this flag, only show matches.')
    parser.add_argument(
        '--prefix',
        default='sahil_storage/ingestion/live/',
        help='Blob name prefix to scan for test artifacts.',
    )
    parser.add_argument(
        '--contains',
        default='',
        help='Optional extra filter: only keep blobs whose name contains this text.',
    )
    parser.add_argument(
        '--top',
        type=int,
        default=2000,
        help='Maximum number of blobs to evaluate in one run.',
    )
    parser.add_argument(
        '--write-report',
        default='blob_cleanup_report.json',
        help='Local JSON report file path.',
    )
    return parser


def build_blob_service_client() -> tuple[BlobServiceClient, str]:
    load_dotenv()

    container_name = os.getenv('AZURE_STORAGE_CONTAINER_NAME', '').strip()
    connection_string = os.getenv('AZURE_STORAGE_CONNECTION_STRING', '').strip()
    account_url = os.getenv('AZURE_STORAGE_ACCOUNT_URL', '').strip()

    if not container_name:
        raise RuntimeError('AZURE_STORAGE_CONTAINER_NAME is not set.')

    if connection_string:
        return BlobServiceClient.from_connection_string(connection_string), container_name

    if account_url:
        return BlobServiceClient(account_url=account_url, credential=DefaultAzureCredential()), container_name

    raise RuntimeError('Set either AZURE_STORAGE_CONNECTION_STRING or AZURE_STORAGE_ACCOUNT_URL.')


def list_matches(*, blob_service_client: BlobServiceClient, container_name: str, prefix: str, contains: str, top: int) -> list[dict[str, Any]]:
    container_client = blob_service_client.get_container_client(container_name)
    matches: list[dict[str, Any]] = []

    for index, blob in enumerate(container_client.list_blobs(name_starts_with=prefix), start=1):
        if index > top:
            break
        blob_name = blob.name
        if contains and contains not in blob_name:
            continue
        matches.append(
            {
                'name': blob_name,
                'size_bytes': getattr(blob, 'size', None),
                'last_modified': blob.last_modified.isoformat() if getattr(blob, 'last_modified', None) else None,
            }
        )

    return matches


def delete_matches(*, blob_service_client: BlobServiceClient, container_name: str, matches: list[dict[str, Any]]) -> int:
    if not matches:
        return 0

    container_client = blob_service_client.get_container_client(container_name)
    deleted_count = 0

    for item in matches:
        blob_name = item['name']
        container_client.delete_blob(blob_name, delete_snapshots='include')
        deleted_count += 1

    return deleted_count


def main() -> int:
    args = build_parser().parse_args()
    dry_run = not args.yes

    blob_service_client, container_name = build_blob_service_client()
    matches = list_matches(
        blob_service_client=blob_service_client,
        container_name=container_name,
        prefix=args.prefix,
        contains=args.contains,
        top=args.top,
    )

    total_bytes = sum(int(item['size_bytes'] or 0) for item in matches)
    report = {
        'timestamp': datetime.now(UTC).isoformat(),
        'mode': 'DRY-RUN' if dry_run else 'DELETE',
        'container_name': container_name,
        'prefix': args.prefix,
        'contains': args.contains,
        'matched_count': len(matches),
        'matched_total_bytes': total_bytes,
        'matches': matches,
        'deleted_count': 0,
    }

    print('=== Azure Blob test artifact cleanup ===')
    print(f"Mode            : {report['mode']}")
    print(f"Container       : {container_name}")
    print(f"Prefix          : {args.prefix or '<none>'}")
    print(f"Contains        : {args.contains or '<none>'}")
    print(f"Matched blobs   : {len(matches)}")
    print(f"Matched bytes   : {total_bytes}")

    for item in matches[:25]:
        print(f"  - {item['name']} | size={item['size_bytes']} | last_modified={item['last_modified']}")
    if len(matches) > 25:
        print(f"  ... and {len(matches) - 25} more")

    if dry_run:
        print('Dry-run only. Re-run with --yes to actually delete blobs.')
    else:
        deleted_count = delete_matches(
            blob_service_client=blob_service_client,
            container_name=container_name,
            matches=matches,
        )
        report['deleted_count'] = deleted_count
        print(f"Deleted blobs   : {deleted_count}")

    report_path = Path(args.write_report).resolve()
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"Report written   : {report_path}")

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
