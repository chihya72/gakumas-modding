"""Local developer smoke test for the frozen HSKI game-data contract."""

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.audit_profile import audit


profile_dir = ROOT / "profiles" / "hski-cstm-0000"
report = audit(profile_dir)
assert report["result"] == "pass", [
    item for item in report["checks"] if item["status"] == "fail"
]
contract = report["contract"]
assert contract["geometry"]["vertexCount"] == 17615
assert contract["geometry"]["indexCount"] == 74664
assert contract["skinning"]["bindPoseCount"] == 152
assert contract["skinning"]["sourceActiveBoneCount"] == 147
assert contract["skinning"]["numericallyUnobservableBones"] == [
    "RightFrontRibbon1_S"
]
assert contract["skinning"]["regionMap"]["regionCount"] == 387
assert len(contract["passes"]["stableSignatureSessions"]) == 8
assert all(
    item["conforms"] for item in contract["passes"]["stableSignatureSessions"]
)
print("GMI_PROFILE_CONTRACT_OK", report["summary"])
