"""R4-WS3 (D and K) document, asset and independent-recompute tests.

The two-node reference implementation below is written from the circuit
equations directly.  It deliberately does not import design-hardware/scripts/
calculate.py or any other project module.
"""

import hashlib
import json
import math
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DH = ROOT / "design-hardware"
REF = DH / "references" / "decisions"
CASES = REF / "cases"
ASSETS = DH / "assets" / "decisions"

D01_REF = REF / "d01-tolerance-and-worst-case.md"
K01_REF = REF / "k01-controlled-experiment.md"
D01_CASE = CASES / "r4-case-d01-acquisition-tolerance.md"
K01_CASE = CASES / "r4-case-k01-acquisition-single-variable.md"
TOL_TPL = ASSETS / "tolerance-budget.template.md"
EXP_TPL = ASSETS / "experiment-record.template.md"
RECOMPUTE = ASSETS / "adc-settle.r4p3.recompute.json"
SOURCE_REGISTER = DH / "references" / "source-register.md"

OWNED = [D01_REF, K01_REF, D01_CASE, K01_CASE, TOL_TPL, EXP_TPL, RECOMPUTE]

REFERENCE_HEADINGS = [
    "## 目录",
    "## 1. 触发条件",
    "## 2. 输入",
    "## 3. Agent 可独立完成的判断",
    "## 4. 必须停下的条件",
    "## 5. 决策规则与表",
    "## 6. 改变哪个工程决定",
    "## 7. 完整案例",
    "## 8. 证据与验证方式",
    "## 9. 与现有资产的分工",
    "## 10. 来源、未知与重评触发",
]
CASE_HEADINGS = [
    "## 1. 触发与用户任务",
    "## 2. 产品与真实材料",
    "## 3. 初始决定（错在哪）",
    "## 4. 判定依据（path:start-end）",
    "## 5. 修正后的决定、代价与三行用户可见摘要",
    "## 6. 记录类型与 typed block",
    "## 7. 验证与证据状态",
    "## 8. 未知、停止与重评",
    "## 9. 与现有资产分工",
]


def read_text(path):
    return path.read_text(encoding="utf-8")


def frontmatter(text):
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---", 4)
    if end < 0:
        return {}
    data = {}
    for line in text[4:end].splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            data[key.strip()] = value.strip()
    return data


def section(text, heading):
    start = text.index(heading)
    nxt = text.find("\n## ", start + len(heading))
    return text[start:] if nxt < 0 else text[start:nxt]


def line_count(text):
    return len(text.splitlines())


def two_node_residual(rs, rw, ce, cs, t):
    """Independent closed form for the two-node RC network.

    Node equations:
      Ce*dVa/dt = (Vs-Va)/Rs - (Va-Vb)/Rw
      Cs*dVb/dt = (Va-Vb)/Rw
    With Vs a unit step and zero initial voltages, Vb(t) is 1-residual(t).
    """
    if rs < 0 or rw < 0 or ce <= 0 or cs <= 0 or t < 0:
        raise ValueError("invalid RC parameters")
    if rs == 0 and rw == 0:
        raise ValueError("at least one resistance must be positive")
    if rs == 0:
        return math.exp(-t / (rw * cs))
    if rw == 0:
        return math.exp(-t / (rs * (ce + cs)))
    u = 1.0 / (rs * ce)
    v = 1.0 / (rw * ce)
    w = 1.0 / (rw * cs)
    a = u + v + w
    disc = math.sqrt(max(0.0, a * a - 4.0 * u * w))
    fast = (a + disc) / 2.0
    slow = (a - disc) / 2.0
    if abs(fast - slow) <= 1e-15 * fast:
        return (1.0 + slow * t) * math.exp(-slow * t)
    return (fast * math.exp(-slow * t) - slow * math.exp(-fast * t)) / (fast - slow)


def two_node_lsb(rs, rw, ce, cs, t, bits=12):
    if not isinstance(bits, int) or bits < 1:
        raise ValueError("bits must be a positive integer")
    return two_node_residual(rs, rw, ce, cs, t) * (2 ** bits)


def single_pole_lsb(rs, rw, ce, cs, t, bits=12):
    if rs + rw <= 0:
        raise ValueError("total resistance must be positive")
    if ce + cs <= 0:
        raise ValueError("total capacitance must be positive")
    return math.exp(-t / ((rs + rw) * (ce + cs))) * (2 ** bits)


def rk4_lsb(rs, rw, ce, cs, t, bits=12, dt=1e-10):
    if rs <= 0 or rw <= 0:
        raise ValueError("rk4 helper requires positive resistances")
    steps = int(round(t / dt))
    if steps <= 0:
        raise ValueError("t must be at least one step")
    va = 0.0
    vb = 0.0

    def deriv(a, b):
        return ((1.0 - a) / rs - (a - b) / rw) / ce, ((a - b) / rw) / cs

    for _ in range(steps):
        k1a, k1b = deriv(va, vb)
        k2a, k2b = deriv(va + dt * k1a / 2.0, vb + dt * k1b / 2.0)
        k3a, k3b = deriv(va + dt * k2a / 2.0, vb + dt * k2b / 2.0)
        k4a, k4b = deriv(va + dt * k3a, vb + dt * k3b)
        va += dt * (k1a + 2.0 * k2a + 2.0 * k3a + k4a) / 6.0
        vb += dt * (k1b + 2.0 * k2b + 2.0 * k3b + k4b) / 6.0
    return (1.0 - vb) * (2 ** bits)


def registered_sources():
    text = read_text(SOURCE_REGISTER)
    return set(re.findall(r"\|\s*([A-Z]+-S\d+)\s*\|", text))


class EncodingAndOwnership(unittest.TestCase):
    def test_owned_files_exist(self):
        for path in OWNED:
            with self.subTest(path=str(path)):
                self.assertTrue(path.is_file(), path)

    def test_utf8_no_bom_lf_no_replacement_char(self):
        for path in OWNED + [Path(__file__)]:
            with self.subTest(path=str(path)):
                data = path.read_bytes()
                self.assertFalse(data.startswith(b"\xef\xbb\xbf"), "BOM")
                self.assertNotIn(b"\r\n", data, "CRLF")
                text = data.decode("utf-8")
                self.assertNotIn(chr(0xFFFD), text)

    def test_no_todo_marker(self):
        for path in OWNED:
            with self.subTest(path=str(path)):
                self.assertNotIn("[TODO", read_text(path))


class ReferenceDocuments(unittest.TestCase):
    def test_frontmatter_and_headings(self):
        expected = {D01_REF: ("R4-D", "[D]"), K01_REF: ("R4-K", "[K]")}
        for path, (doc_id, package) in expected.items():
            with self.subTest(path=path.name):
                text = read_text(path)
                meta = frontmatter(text)
                self.assertEqual(meta.get("id"), doc_id)
                self.assertEqual(meta.get("packages"), package)
                self.assertEqual(meta.get("evidence"), "E3")
                self.assertEqual(meta.get("last_reviewed"), "2026-10-22")
                self.assertTrue(meta.get("sources"))
                last = -1
                for heading in REFERENCE_HEADINGS:
                    pos = text.find(heading)
                    self.assertGreaterEqual(pos, 0, heading)
                    self.assertGreater(pos, last, heading)
                    last = pos

    def test_line_budget(self):
        for path in (D01_REF, K01_REF):
            with self.subTest(path=path.name):
                n = line_count(read_text(path))
                self.assertGreaterEqual(n, 60)
                self.assertLessEqual(n, 100)

    def test_section9_has_at_least_two_path_ranges(self):
        for path in (D01_REF, K01_REF):
            with self.subTest(path=path.name):
                body = section(read_text(path), "## 9. 与现有资产的分工")
                self.assertLessEqual(line_count(body), 8)
                refs = re.findall(r"[A-Za-z0-9_./-]+\.md:\d+-\d+", body)
                self.assertGreaterEqual(len(refs), 2, body)

    def test_package_subitems_are_named(self):
        d_text = read_text(D01_REF)
        for label in ("D1", "D2", "D3", "D4", "D5", "D6"):
            self.assertIn(label, d_text)
        k_text = read_text(K01_REF)
        for label in ("K1", "K2", "K3", "K4", "K5", "K6"):
            self.assertIn(label, k_text)

    def test_source_ids_are_registered(self):
        registered = registered_sources()
        for path in (D01_REF, K01_REF, D01_CASE, K01_CASE):
            with self.subTest(path=path.name):
                meta = frontmatter(read_text(path))
                ids = re.findall(r"\b([A-Z]+-S\d+)\b", meta.get("sources", ""))
                self.assertTrue(ids)
                self.assertEqual(sorted(set(ids) - registered), [])
        asset_ids = set(json.loads(read_text(RECOMPUTE)).get("sources", []))
        self.assertTrue(asset_ids)
        self.assertEqual(sorted(asset_ids - registered), [])

    def test_no_bench_verification_claim(self):
        text = read_text(K01_REF)
        self.assertIn("没有 bench 不写 verified", text)
        self.assertIn("没有分布/相关性不做蒙特卡洛", text)

    def test_markdown_links_resolve(self):
        for path in (D01_REF, K01_REF, D01_CASE, K01_CASE):
            with self.subTest(path=path.name):
                for target in re.findall(r"\[[^\]]+\]\(([^)]+)\)", read_text(path)):
                    if target.startswith(("http://", "https://", "#", "mailto:")):
                        continue
                    clean = target.split("#", 1)[0]
                    self.assertTrue((path.parent / clean).is_file(), target)

    def test_no_unmarked_c_numbers(self):
        for path in OWNED:
            if path.suffix not in (".md", ".json"):
                continue
            for number, line in enumerate(read_text(path).splitlines(), 1):
                if re.search(r"\bC\d{2,}\b", line):
                    self.assertTrue(
                        any(mark in line for mark in ("待查", "示例", "未核对")),
                        f"{path.name}:{number}: unmarked C number",
                    )


class CaseDocuments(unittest.TestCase):
    def test_frontmatter(self):
        expected = {
            D01_CASE: ("R4-CASE-D01", "[D]", "refuted-assumption"),
            K01_CASE: ("R4-CASE-K01", "[K]", "unknown-retained"),
        }
        for path, (case_id, package, record_type) in expected.items():
            with self.subTest(path=path.name):
                meta = frontmatter(read_text(path))
                self.assertEqual(meta.get("id"), case_id)
                self.assertEqual(meta.get("project"), "R4-P3")
                self.assertEqual(meta.get("family"), "P02")
                self.assertEqual(meta.get("parent"), "P02")
                self.assertEqual(meta.get("packages"), package)
                self.assertEqual(meta.get("evidence"), "E3")
                self.assertEqual(meta.get("execution"), "OFFLINE_PLANNING")
                self.assertEqual(meta.get("hardware_execution"), "NOT RUN")
                self.assertEqual(meta.get("last_reviewed"), "2026-10-22")
                self.assertTrue(meta.get("facts_source"))
                self.assertIn(record_type, meta.get("record_types", ""))
                for heading in CASE_HEADINGS:
                    self.assertIn(heading, read_text(path))

    def test_line_budget(self):
        for path in (D01_CASE, K01_CASE):
            with self.subTest(path=path.name):
                n = line_count(read_text(path))
                self.assertGreaterEqual(n, 50)
                self.assertLessEqual(n, 90)

    def test_three_line_user_summary(self):
        for path in (D01_CASE, K01_CASE):
            with self.subTest(path=path.name):
                body = section(read_text(path), "## 5. 修正后的决定、代价与三行用户可见摘要")
                self.assertIn("- 决定：", body)
                self.assertIn("- 代价：", body)
                self.assertIn("- 下一个检查或待查：", body)

    def test_typed_block_matches_record_type(self):
        d_text = read_text(D01_CASE)
        self.assertIn("### refuted-assumption", d_text)
        self.assertIn("原假设", d_text)
        self.assertIn("反证", d_text)
        self.assertIn("状态：corrected", d_text)
        k_text = read_text(K01_CASE)
        self.assertIn("### unknown-retained", k_text)
        for field in ("未知项", "为什么影响决定", "owner", "停止条件", "复评触发"):
            self.assertIn(field, k_text)

    def test_execution_status_is_visible(self):
        for path in (D01_CASE, K01_CASE):
            with self.subTest(path=path.name):
                text = read_text(path)
                self.assertIn("board_verified:false", text)
                self.assertIn("NOT RUN", text)

    def test_d01_has_required_independent_items(self):
        text = read_text(D01_CASE)
        for term in ("VREF_INIT", "MUX_CROSSTALK", "CAL_RESIDUAL", "TEMP_FIELD"):
            self.assertIn(term, text)
        self.assertIn("共用基准", text)

    def test_d01_cites_existing_budget_and_recompute(self):
        text = read_text(D01_CASE)
        self.assertIn("p02-industrial-rs485-analog.md:169-190", text)
        self.assertIn("3740.25", text)
        self.assertIn("3905.53", text)
        self.assertIn("0.5239", text)
        self.assertIn("2.27e-36", text)

    def test_k01_prereg_fields(self):
        text = read_text(K01_CASE)
        for field in ("target", "guardrails", "factor", "levels", "controls",
                      "response", "stop", "validity", "adoption"):
            self.assertIn(field, text)
        self.assertIn("2、5、10、20、50 µs", text)
        self.assertIn("0.5 LSB", text)


class CaseContentCompleteness(unittest.TestCase):
    def test_template_paths_are_named(self):
        self.assertIn("tolerance-budget.template.md", read_text(D01_CASE))
        self.assertIn("experiment-record.template.md", read_text(K01_CASE))

    def test_d01_conditional_has_owner_and_deadline(self):
        text = read_text(D01_CASE)
        self.assertIn("owner=硬件负责人", text)
        self.assertIn("到期日=首板 bring-up 前", text)
        self.assertIn("不得写 guaranteed_pass", text)

    def test_d01_action_table_covers_dominant_terms(self):
        text = read_text(D01_CASE)
        self.assertIn("主导项动作", text)
        for action in ("两点 4/20 mA 校准", "多点温度校准", "提高校准源",
                       "每通道缓冲", "更高位数 ADC"):
            self.assertIn(action, text)

    def test_d01_calibration_state_uses_template_enum(self):
        text = read_text(D01_CASE)
        self.assertNotIn("not-calibratable/periodic", text)
        self.assertNotIn("n/a（系统项）", text)
        self.assertIn("not-calibratable", text)

    def test_d01_path_citations_are_located(self):
        text = read_text(D01_CASE)
        self.assertIn(
            "`P02`=`design-hardware/references/projects/p02-industrial-rs485-analog.md`",
            text,
        )
        self.assertIn("C1:179-191", text)
        self.assertIn("P02:205-205", text)
        self.assertIn("P02:82-82", text)
        self.assertIn(":73-73", text)
        self.assertIn(":498-498", text)
        self.assertIn("JSON:buffered-470pF-10us", text)

    def test_k01_preregistration_is_reproducible(self):
        text = read_text(K01_CASE)
        for token in (
            "t_ACQ_ref=1 ms",
            "residual(t_ACQ)=code(t_ACQ)-code_ref",
            "有效样本 ≥8/10",
            "不按结果剔除离群点",
            "ensure_ascii=False",
        ):
            self.assertIn(token, text)


class Templates(unittest.TestCase):
    def test_header_and_line_budget(self):
        for path in (TOL_TPL, EXP_TPL):
            with self.subTest(path=path.name):
                text = read_text(path)
                self.assertIn("Agent 填写，用户不填", text.splitlines()[0])
                n = line_count(text)
                self.assertGreaterEqual(n, 25)
                self.assertLessEqual(n, 60)

    def test_tolerance_template_fields(self):
        text = read_text(TOL_TPL)
        for field in ("term", "min", "typ", "max", "unit", "condition",
                      "temp_range", "evidence_grade", "class", "correlated_group",
                      "calibration_state", "source", "worst", "RSS",
                      "dominant_rank", "decision"):
            self.assertIn(field, text)
        for state in ("guaranteed_pass", "statistical_pass", "conditional",
                      "fail", "cannot_conclude"):
            self.assertIn(state, text)

    def test_experiment_template_fields(self):
        text = read_text(EXP_TPL)
        for field in ("target", "guardrails", "baseline", "factor", "levels",
                      "controls", "response", "stop", "validity", "adoption"):
            self.assertIn(field, text)
        self.assertIn("没有 bench 不写 verified", text)
        self.assertIn("蒙特卡洛", text)

    def test_templates_declare_used_by(self):
        self.assertIn("used_by: `R4-CASE-D01`", read_text(TOL_TPL))
        self.assertIn("used_by: `R4-CASE-K01`", read_text(EXP_TPL))


class RecomputeAsset(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads(read_text(RECOMPUTE))
        cls.cases = {case["id"]: case for case in cls.data["recompute_cases"]}

    def test_top_level_fields(self):
        data = self.data
        self.assertEqual(data["schema_version"], 1)
        self.assertEqual(data["id"], "adc-settle.r4p3.recompute")
        self.assertEqual(data["project"], "R4-P3")
        self.assertEqual(data["parent"], "P02")
        self.assertEqual(data["evidence"], "E3")
        self.assertEqual(data["execution"], "OFFLINE_PLANNING")
        self.assertEqual(data["hardware_execution"], "NOT RUN")
        self.assertIs(data["board_verified"], False)
        self.assertTrue(data["not_checked"])
        self.assertTrue(data["sources"])

    def test_p02_claims_are_preserved(self):
        claims = {c["id"]: c for c in self.data["p02_claims"]}
        self.assertEqual(claims["direct-unbuffered"]["claimed_error_lsb"], 3905)
        self.assertEqual(claims["buffered-1nF"]["claimed_error_lsb"], 0.524)
        for claim in claims.values():
            self.assertEqual(claim["method_identified"], "single_pole_proxy")
            self.assertIn("p02-industrial-rs485-analog.md", claim["where"])

    def test_case_parameters(self):
        direct = self.cases["direct-unbuffered"]["parameters"]
        self.assertEqual(direct, {
            "r_source_ohm": 1100,
            "r_switch_ohm": 1000,
            "c_ext_F": 1e-7,
            "c_sample_F": 5e-12,
            "t_sample_s": 1e-5,
            "bits": 12,
            "vref_V": 2.5,
        })
        buffered = self.cases["buffered-1nF"]["parameters"]
        self.assertEqual(buffered["r_source_ohm"], 110)
        self.assertEqual(buffered["r_switch_ohm"], 1000)
        self.assertEqual(buffered["c_ext_F"], 1e-9)
        self.assertEqual(buffered["c_sample_F"], 5e-12)
        self.assertEqual(buffered["t_sample_s"], 1e-5)
        self.assertEqual(buffered["bits"], 12)
        for case_id, t_sample in (
            ("buffered-470pF-2us", 2e-6),
            ("buffered-470pF-5us", 5e-6),
            ("buffered-470pF-10us", 1e-5),
        ):
            with self.subTest(case=case_id):
                p = self.cases[case_id]["parameters"]
                self.assertEqual(p["r_source_ohm"], 110)
                self.assertEqual(p["r_switch_ohm"], 1000)
                self.assertEqual(p["c_ext_F"], 4.7e-10)
                self.assertEqual(p["c_sample_F"], 5e-12)
                self.assertEqual(p["t_sample_s"], t_sample)
                self.assertEqual(p["bits"], 12)
                self.assertEqual(p["vref_V"], 2.5)

    def test_independent_two_node_matches_asset(self):
        for case_id, case in self.cases.items():
            p = case["parameters"]
            actual = two_node_lsb(
                p["r_source_ohm"], p["r_switch_ohm"], p["c_ext_F"],
                p["c_sample_F"], p["t_sample_s"], p["bits"],
            )
            expected = case["two_node"]["error_lsb"]
            with self.subTest(case=case_id):
                self.assertTrue(
                    math.isclose(actual, expected, rel_tol=1e-12, abs_tol=1e-300),
                    (actual, expected),
                )

    def test_independent_single_pole_matches_asset(self):
        for case_id, case in self.cases.items():
            p = case["parameters"]
            actual = single_pole_lsb(
                p["r_source_ohm"], p["r_switch_ohm"], p["c_ext_F"],
                p["c_sample_F"], p["t_sample_s"], p["bits"],
            )
            expected = case["single_pole"]["error_lsb"]
            with self.subTest(case=case_id):
                self.assertTrue(math.isclose(actual, expected, rel_tol=1e-12, abs_tol=1e-15))

    def test_difference_arithmetic(self):
        for case_id, case in self.cases.items():
            difference = case["two_node"]["error_lsb"] - case["single_pole"]["error_lsb"]
            with self.subTest(case=case_id):
                self.assertTrue(math.isclose(case["difference"]["error_lsb"], difference, rel_tol=1e-12, abs_tol=1e-30))
                pct = difference / case["single_pole"]["error_lsb"] * 100.0
                self.assertTrue(math.isclose(case["difference"]["percent"], pct, rel_tol=1e-12, abs_tol=1e-12))

    def test_decisions(self):
        self.assertEqual(self.cases["direct-unbuffered"]["decision"], "fail")
        self.assertEqual(self.cases["buffered-1nF"]["decision"], "conditional")
        self.assertEqual(self.cases["direct-unbuffered"]["two_node"]["status"], "fail")
        self.assertEqual(self.cases["buffered-1nF"]["two_node"]["status"], "pass")
        for case_id in ("buffered-470pF-2us", "buffered-470pF-5us", "buffered-470pF-10us"):
            with self.subTest(case=case_id):
                self.assertEqual(self.cases[case_id]["decision"], "conditional")
                self.assertEqual(self.cases[case_id]["two_node"]["status"], "pass")

    def test_baseline_hash_covers_model_and_cases(self):
        payload = {
            "model": self.data["model"],
            "recompute_cases": self.data["recompute_cases"],
        }
        actual = hashlib.sha256(
            json.dumps(
                payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
            ).encode("utf-8")
        ).hexdigest()
        canonicalization = self.data["canonicalization"]
        self.assertEqual(
            sorted(canonicalization["payload_scope"]), ["model", "recompute_cases"]
        )
        self.assertIn("ensure_ascii=False", canonicalization["method"])
        self.assertIn("separators=(',', ':')", canonicalization["method"])
        self.assertEqual(canonicalization["sha256"], actual)
        case_text = read_text(K01_CASE)
        hashes = re.findall(r"\b[0-9a-f]{64}\b", case_text)
        self.assertEqual(hashes, [actual])

    def test_all_json_numbers_are_finite(self):
        def walk(value):
            if isinstance(value, dict):
                for item in value.values():
                    walk(item)
            elif isinstance(value, list):
                for item in value:
                    walk(item)
            elif isinstance(value, float):
                self.assertTrue(math.isfinite(value))

        walk(self.data)


class IndependentTruth(unittest.TestCase):
    # Fixtures 1-3 duplicate the asset values on purpose: they are an asset
    # regression check, not independent hand values.  The hand-derived
    # fixture below is derived from a different analytic route.
    ASSET_REGRESSION_FIXTURES = [
        (1100, 1000, 100e-9, 5e-12, 10e-6, 3740.247528379189),
        (110, 1000, 1e-9, 5e-12, 10e-6, 2.2735810902502267e-36),
        (1000, 1000, 1e-9, 1e-9, 10e-6, 105.19447165261134),
        (100, 1000, 1e-9, 1e-9, 10e-6, 0.5447777451192511),
        (1000, 1000, 1e-9, 1e-9, 1e-6, 3222.100374746597),
    ]
    # Symmetric network Rs=Rw=R, Ce=Cs=C.  With k=1/(R*C) the two rates are
    # l1=(3+sqrt(5))*k/2 and l2=(3-sqrt(5))*k/2, so the residual follows from
    # that hand formula rather than from the general quadratic solver:
    # residual(t)=(l1*exp(-l2*t)-l2*exp(-l1*t))/(l1-l2).
    # R=470 ohm, C=2.2 nF, t=8 us gives 249.6902757177953 LSB by hand.
    HAND_FIXTURES = [
        (470.0, 470.0, 2.2e-9, 2.2e-9, 8e-6, 249.6902757177953),
    ]

    def test_asset_regression_fixtures(self):
        for rs, rw, ce, cs, t, expected in self.ASSET_REGRESSION_FIXTURES:
            with self.subTest(rs=rs, rw=rw, ce=ce, cs=cs, t=t):
                actual = two_node_lsb(rs, rw, ce, cs, t, 12)
                self.assertTrue(
                    math.isclose(actual, expected, rel_tol=1e-9, abs_tol=1e-12),
                    (actual, expected),
                )

    def test_hand_derived_symmetric_network(self):
        for rs, rw, ce, cs, t, expected in self.HAND_FIXTURES:
            with self.subTest(rs=rs, rw=rw, ce=ce, cs=cs, t=t):
                actual = two_node_lsb(rs, rw, ce, cs, t, 12)
                self.assertTrue(
                    math.isclose(actual, expected, rel_tol=1e-9, abs_tol=1e-12),
                    (actual, expected),
                )

    def test_rk4_cross_check(self):
        closed = two_node_lsb(1000, 1000, 1e-9, 1e-9, 10e-6, 12)
        numeric = rk4_lsb(1000, 1000, 1e-9, 1e-9, 10e-6, 12, dt=1e-10)
        self.assertTrue(math.isclose(closed, numeric, rel_tol=1e-6, abs_tol=1e-6), (closed, numeric))

    def test_zero_source_branch(self):
        actual = two_node_lsb(0, 1000, 1e-9, 5e-12, 10e-6, 12)
        expected = math.exp(-10e-6 / (1000 * 5e-12)) * 4096
        self.assertTrue(math.isclose(actual, expected, rel_tol=1e-12))

    def test_zero_switch_branch(self):
        actual = two_node_lsb(100, 0, 1e-9, 5e-12, 10e-6, 12)
        expected = math.exp(-10e-6 / (100 * (1e-9 + 5e-12))) * 4096
        self.assertTrue(math.isclose(actual, expected, rel_tol=1e-12))

    def test_invalid_inputs(self):
        with self.assertRaises(ValueError):
            two_node_lsb(0, 0, 1e-9, 5e-12, 10e-6, 12)
        with self.assertRaises(ValueError):
            two_node_lsb(100, 1000, 1e-9, 5e-12, 10e-6, 0)
        with self.assertRaises(ValueError):
            two_node_lsb(-1, 1000, 1e-9, 5e-12, 10e-6, 12)

    def test_error_decreases_with_longer_acquisition(self):
        short = two_node_lsb(1100, 1000, 1e-7, 5e-12, 5e-6, 12)
        nominal = two_node_lsb(1100, 1000, 1e-7, 5e-12, 10e-6, 12)
        long = two_node_lsb(1100, 1000, 1e-7, 5e-12, 20e-6, 12)
        self.assertGreater(short, nominal)
        self.assertGreater(nominal, long)
        self.assertGreater(long, 0.0)

    def test_test_file_does_not_import_calculate(self):
        source = read_text(Path(__file__))
        needle_import = "import " + "calculate"
        needle_from = "from " + "calculate"
        needle_scripts = "scripts" + "." + "calculate"
        self.assertNotIn(needle_import, source)
        self.assertNotIn(needle_from, source)
        self.assertNotIn(needle_scripts, source)


class D01BudgetArithmetic(unittest.TestCase):
    """Recompute the D01 summary numbers from the table cells themselves."""

    @staticmethod
    def budget_rows():
        rows = {}
        for line in read_text(D01_CASE).splitlines():
            if not line.startswith("| "):
                continue
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            if len(cells) >= 17 and re.fullmatch(r"[A-Z][A-Z0-9_]*", cells[0]):
                rows[cells[0]] = cells
        return rows

    @staticmethod
    def max_ua(rows, key):
        cells = rows[key]
        value = float(cells[4])
        if cells[5] == "LSB":
            value *= 6.1035
        return value

    def components(self):
        rows = self.budget_rows()
        return (
            self.max_ua(rows, "SHUNT_INIT"),
            self.max_ua(rows, "GAIN_INIT"),
            self.max_ua(rows, "VREF_INIT"),
            self.max_ua(rows, "VOS_INIT"),
            self.max_ua(rows, "QUANT"),
            self.max_ua(rows, "TEMP_FIELD"),
        )

    def test_worst_rss_and_mixed_bounds(self):
        a, b, c, d, q, tf = self.components()
        self.assertAlmostEqual(a + b + c + d + q, 63.05, delta=0.01)
        self.assertAlmostEqual(
            math.sqrt(a * a + b * b + c * c + d * d + q * q), 31.77, delta=0.01
        )
        self.assertAlmostEqual(
            c + math.sqrt(a * a + b * b + d * d + q * q), 44.68, delta=0.01
        )
        self.assertAlmostEqual(a + b + c + d + q + tf, 108.05, delta=0.01)

    def test_corner_scaling_values(self):
        a, b, c, d, q, tf = self.components()
        # 4 mA scales the gain-class terms by 4/20 = 0.2; Vos and quantization
        # do not scale with the reading.
        self.assertAlmostEqual(0.2 * (a + b + c) + d + q, 23.05, delta=0.01)
        self.assertAlmostEqual(
            0.2 * (a + b + c) + d + q + 0.2 * tf, 32.05, delta=0.01
        )
        self.assertAlmostEqual(a + b + c + d + q + 35.0, 98.05, delta=0.01)
        # CAL_RESIDUAL must not be added on top of TEMP_FIELD: the full-temp
        # post-cal number is driven by CAL_RESIDUAL alone.
        text = read_text(D01_CASE)
        self.assertIn("post-cal 汇总只取 CAL_RESIDUAL", text)
        self.assertNotIn("≥45（下限", text)
        self.assertIn("最坏情况预算", text)
        self.assertIn("总误差暂不能定论", text)


class K01ModelPrediction(unittest.TestCase):
    def test_470pf_predictions_are_recomputable(self):
        expected = ((2e-6, 1.1e-13), (5e-6, 1.4e-38), (10e-6, 4.3e-80))
        for t, value in expected:
            actual = two_node_lsb(110, 1000, 470e-12, 5e-12, t, 12)
            with self.subTest(t=t):
                self.assertLess(
                    abs(math.log10(actual) - math.log10(value)),
                    0.05,
                    (actual, value),
                )
        self.assertIn("1.1e-13/1.4e-38/4.3e-80", read_text(K01_CASE))


if __name__ == "__main__":
    unittest.main()
