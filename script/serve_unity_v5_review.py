"""Serve one frozen V5 development review split and save reviewer choices locally."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import NamedTemporaryFile
from threading import Lock
from typing import cast

from adaptive_astc.utils.artifacts import ArtifactStore as A

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "experiment report/unity-v5-20261119"
DEVELOPMENT = ROOT / "experiment report/.local/unity-v5-20261119/development-evaluation-v1"
HEADER = ("id", "visible_gradient_banding", "comment")
CHOICES = ("yes", "no", "uncertain")


class Review:
    def __init__(
        self, packet: Path, manifest_sha256: str, output: Path, phase: str = "calibration"
    ) -> None:
        manifest = packet / "manifest.json"
        if A.sha256_file(manifest) != manifest_sha256:
            raise ValueError("The calibration manifest changed after model selection")
        self.manifest_sha256 = manifest_sha256
        self.phase = phase
        self.directory = packet / phase
        self.template = self.directory / "ratings.csv"
        self.output = output
        self.images: dict[str, str] = {}
        self.ids: list[str] = []
        for row in A.read_json(manifest)["strata"][phase]["rows"]:
            image_id = str(row["id"])
            filenames = row["display_sha256"]
            expected = {f"{image_id}-{kind}.png" for kind in ("reference", "decoded")}
            if (
                image_id != f"{row['index']:04d}"
                or image_id in self.ids
                or filenames.keys() != expected
            ):
                raise ValueError("The frozen review image list is invalid")
            self.ids.append(image_id)
            self.images.update(filenames)
        if not self.ids:
            raise ValueError("The review pack has no images")
        self.read_ratings()

    def read_ratings(self) -> dict[str, tuple[str, str]]:
        ratings_path = self.output if self.output.exists() else self.template
        with ratings_path.open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            rows = list(reader)
            if reader.fieldnames != list(HEADER):
                raise ValueError("Unexpected review CSV columns")
            ratings = {row["id"]: (row[HEADER[1]], row["comment"]) for row in rows}
            if (
                set(ratings) != set(self.ids)
                or len(rows) != len(self.ids)
                or any(
                    vote not in ("", *CHOICES) or note is None for vote, note in ratings.values()
                )
            ):
                raise ValueError("The local rating CSV does not match the frozen review list")
        return ratings

    def save_rating(self, image_id: str, choice: str) -> None:
        ratings = self.read_ratings()
        ratings[image_id] = (choice, ratings[image_id][1])
        with NamedTemporaryFile(
            mode="w", encoding="utf-8-sig", newline="", dir=self.output.parent, delete=False
        ) as stream:
            temporary = Path(stream.name)
            try:
                writer = csv.writer(stream)
                writer.writerow(HEADER)
                writer.writerows((key, *ratings[key]) for key in self.ids)
                stream.flush()
                os.fsync(stream.fileno())
                stream.close()
                temporary.replace(self.output)
            finally:
                stream.close()
                temporary.unlink(missing_ok=True)


class ReviewServer(ThreadingHTTPServer):
    allow_reuse_address = False

    def __init__(self, port: int, review: Review) -> None:
        self.review = review
        self.ratings_lock = Lock()
        self.page = Path(__file__).with_name("unity_v5_review.html")
        super().__init__(("127.0.0.1", port), Handler)
        self.host_header = f"127.0.0.1:{self.server_port}"


class Handler(BaseHTTPRequestHandler):
    @property
    def review_server(self) -> ReviewServer:
        return cast(ReviewServer, self.server)

    def log_message(self, format: str, *args: object) -> None:
        if self.command != "GET" or (len(args) > 1 and args[1] != "200"):
            super().log_message(format, *args)

    def send_body(self, status: int, kind: str, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("X-Review-Packet", self.review_server.review.manifest_sha256)
        self.send_header("X-Review-Phase", self.review_server.review.phase)
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, value: object) -> None:
        self.send_body(200, "application/json", json.dumps(value, ensure_ascii=False).encode())

    def do_GET(self) -> None:
        server = self.review_server
        if self.headers.get("Host") != server.host_header:
            self.send_error(403)
        elif self.path == "/":
            self.send_body(200, "text/html; charset=utf-8", server.page.read_bytes())
        elif self.path == "/api/ratings":
            try:
                with server.ratings_lock:
                    current = server.review.read_ratings()
            except (OSError, ValueError):
                self.send_error(500, "Could not read the local ratings")
                return
            self.send_json([{"id": key, "choice": current[key][0]} for key in server.review.ids])
        elif self.path.startswith("/pairs/") and self.path[7:] in server.review.images:
            name = self.path[7:]
            path = server.review.directory / "pairs" / name
            try:
                photo = path.read_bytes()
            except OSError:
                self.send_error(404)
                return
            if hashlib.sha256(photo).hexdigest() != server.review.images[name]:
                self.send_error(409, "The paired image changed")
                return
            self.send_body(200, "image/png", photo)
        else:
            self.send_error(404)

    def do_POST(self) -> None:
        server = self.review_server
        if (
            self.headers.get("Host") != server.host_header
            or self.headers.get("Origin") != f"http://{server.host_header}"
        ):
            self.send_error(403)
            return
        if self.path != "/api/ratings":
            self.send_error(404)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 512 or self.headers.get_content_type() != "application/json":
                raise ValueError("Expected a small JSON choice")
            body = json.loads(self.rfile.read(length))
            if not isinstance(body, dict):
                raise ValueError("Expected a rating object")
            image_id, choice = body.get("id"), body.get("choice")
            if image_id not in server.review.ids or choice not in CHOICES:
                raise ValueError("Unknown image or choice")
        except ValueError:
            self.send_error(400, "Unknown image or choice")
            return
        try:
            with server.ratings_lock:
                server.review.save_rating(image_id, choice)
        except (OSError, ValueError):
            self.send_error(500, "Could not save the local ratings")
            return
        self.send_json({"id": image_id, "choice": choice})


def verify_calibration(packet: Path, manifest_sha256: str, receipt_sha256: str) -> None:
    raw = (DEVELOPMENT / "calibration-human-v1.json").read_bytes()
    if hashlib.sha256(raw).hexdigest() != receipt_sha256:
        raise ValueError("Expected the frozen human calibration receipt")
    selection = json.loads(raw)
    manifest = A.read_json(packet / "manifest.json")
    if (
        selection["status"] != "passed"
        or selection["phase"] != "calibration"
        or selection["confirmation_opened"] is not False
        or selection["binding"]
        != {
            "validation_sha256": manifest["validation_sha256"],
            "packet_sha256": manifest_sha256,
            "partition_sha256": manifest["partition_sha256"],
        }
        or selection["ratings_sha256"]
        != A.sha256_file(DEVELOPMENT / "calibration-ratings-frozen-v1.csv")
    ):
        raise ValueError("The human calibration must match this review packet")


def formal_confirmation_review(expected_sha256: str) -> Review:
    path = PUBLIC / "confirmation-evaluation-v1.json"
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise ValueError("The formal confirmation evaluation receipt changed")
    report = json.loads(raw)
    if (
        report["status"] != "machine_evaluation_complete_awaiting_independent_human_ratings"
        or report["test_opened"] is not True
        or report["images"] != 1000
    ):
        raise ValueError("The complete formal V5 machine evaluation is required")
    packet = Path(report["blind_review_packet"]["path"]).resolve()
    if packet != (
        DEVELOPMENT.parent
        / "confirmation-execution1000-v1/formal-evaluation-v1/blind-review/manifest.json"
    ):
        raise ValueError("The formal review packet escaped its sealed output")
    return Review(
        packet.parent,
        report["blind_review_packet"]["sha256"],
        packet.parents[1] / "confirmation-ratings-web.csv",
        phase="confirmation",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=48765)
    parser.add_argument(
        "--phase", choices=("calibration", "holdout", "confirmation"), default="calibration"
    )
    parser.add_argument("--calibration-sha256")
    parser.add_argument("--evaluation-sha256")
    args = parser.parse_args()
    if args.phase == "confirmation":
        if args.evaluation_sha256 is None:
            parser.error("Bind the completed formal evaluation before opening its blind review")
        review = formal_confirmation_review(args.evaluation_sha256)
    else:
        binding = A.read_json(PUBLIC / "confirmation-model-binding.json")["rating_packet"]
        packet = DEVELOPMENT / "review-packet"
        if Path(binding["path"]).resolve() != (packet / "manifest.json").resolve():
            raise ValueError("Expected the selected development review pack")
        if args.phase == "holdout":
            if args.calibration_sha256 is None:
                parser.error("Verify the human calibration receipt before opening holdout review")
            verify_calibration(packet, binding["sha256"], args.calibration_sha256)
        review = Review(
            packet,
            binding["sha256"],
            DEVELOPMENT / f"{args.phase}-ratings-web.csv",
            phase=args.phase,
        )
    with ReviewServer(args.port, review) as server:
        print(f"V5 {args.phase} review available at http://{server.host_header}/", flush=True)
        server.serve_forever()


if __name__ == "__main__":
    main()
