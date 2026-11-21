# -*- coding: utf-8 -*-
"""Rule-based security review for the Index Calculator Pro QGIS plugin."""
from html import escape
import os
import re

try:
    from qgis.core import QgsProcessingAlgorithm, QgsProcessingParameterFileDestination, QgsProcessingException
except Exception:
    QgsProcessingAlgorithm = None

_RULES = [
    ("CRITICAL", re.compile(r"\beval\s*\("), "Dynamic evaluation of expressions or code"),
    ("CRITICAL", re.compile(r"\bexec\s*\("), "Dynamic execution of code"),
    ("HIGH", re.compile(r"\bos\.system\s*\(|\bsubprocess\.(?:run|Popen|call|check_output)\s*\("), "External process execution; review arguments and shell use"),
    ("HIGH", re.compile(r"\bshell\s*=\s*True\b"), "Shell execution enabled; verify that inputs cannot control commands"),
    (("HIGH"), re.compile(r"\bpickle\.(?:load|loads)\s*\("), "Deserialization of pickle data"),
    ("HIGH", re.compile(r"\byaml\.load\s*\("), "YAML loading; verify safe loader is used"),
    ("MEDIUM", re.compile(r"\brequests\.(?:get|post|put|delete)\s*\("), "Network request; review URL validation, redirects and timeouts"),
    ("MEDIUM", re.compile(r"\b(?:urllib\.request\.urlopen|urlopen)\s*\("), "Network request; review URL validation, redirects and timeouts"),
    ("MEDIUM", re.compile(r"\bos\.path\.join\s*\("), "Path construction; confirm untrusted components are validated"),
    ("MEDIUM", re.compile(r"\b(?:GDAL|gdal)\.(?:Open|OpenEx|Translate|Warp)\s*\("), "GDAL operation; review input size, driver and resource limits"),
    ("LOW", re.compile(r"\b(?:password|passwd|api[_-]?key|secret|token)\s*=\s*['\"](?!['\"])[^'\"]{6,}['\"]", re.I), "Possible hard-coded credential"),
]


def scan_tree(root):
    findings = []
    skipped_dirs = {".git", "__pycache__", "venv", ".venv", "dist", "build"}
    for base, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in skipped_dirs]
        for filename in files:
            if not filename.endswith(".py"):
                continue
            path = os.path.join(base, filename)
            try:
                with open(path, "r", encoding="utf-8", errors="replace") as f:
                    lines = f.readlines()
            except OSError:
                continue
            rel = os.path.relpath(path, root)
            for line_no, line in enumerate(lines, 1):
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                for severity, pattern, description in _RULES:
                    if pattern.search(line):
                        findings.append((severity, rel, line_no, description, stripped[:240]))
    return findings



def _html_report(findings, scanned_files):
    counts = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0}
    for finding in findings:
        counts[finding[0]] += 1
    rows = []
    for severity, path, line_no, description, excerpt in findings:
        rows.append("<tr><td>{}</td><td>{}</td><td>{}</td><td>{}</td><td><code>{}</code></td></tr>".format(
            escape(severity), escape(path), line_no, escape(description), escape(excerpt)))
    if not rows:
        rows.append("<tr><td colspan='5'>No rule-based findings were detected. This does not prove the plugin is secure.</td></tr>")
    return """<!doctype html><html lang='en'><head><meta charset='utf-8'><title>Index Calculator Pro Security Audit</title>
<style>body{{font-family:Segoe UI,Arial,sans-serif;max-width:1200px;margin:28px auto;padding:0 18px;color:#26332b}}table{{border-collapse:collapse;width:100%;font-size:13px}}th,td{{padding:8px;border:1px solid #d7ded9;text-align:left;vertical-align:top}}th{{background:#eef5ef}}code{{white-space:pre-wrap;overflow-wrap:anywhere}}.note{{padding:12px;background:#f4f4f4}}</style></head><body>
<h1>Index Calculator Pro Security Audit</h1><p class='note'>Rule-based static scan. Findings require manual review. This report is not a penetration test and does not confirm exploitability.</p>
<p>Files scanned: {files}</p><p>Critical: {critical} | High: {high} | Medium: {medium} | Low: {low}</p>
<table><thead><tr><th>Level</th><th>File</th><th>Line</th><th>Rule</th><th>Code excerpt</th></tr></thead><tbody>{rows}</tbody></table></body></html>""".format(files=scanned_files, critical=counts["CRITICAL"], high=counts["HIGH"], medium=counts["MEDIUM"], low=counts["LOW"], rows="".join(rows))


if QgsProcessingAlgorithm is not None:
    class PluginSecurityAuditAlgorithm(QgsProcessingAlgorithm):
        OUTPUT = "OUTPUT"
        def name(self): return "plugin_security_audit"
        def displayName(self): return "Plugin Security Audit"
        def group(self): return "Security"
        def groupId(self): return "security"
        def shortHelpString(self):
            return "Scan Python source files for security-sensitive patterns and export a review report. Rule-based results require manual assessment."
        def createInstance(self):
            return PluginSecurityAuditAlgorithm()
        def initAlgorithm(self, config=None):
            self.addParameter(QgsProcessingParameterFileDestination(self.OUTPUT, "Security audit report", "HTML"))
        def processAlgorithm(self, parameters, context, feedback):
            root = os.path.dirname(os.path.abspath(__file__))
            files = sum(1 for base, dirs, names in os.walk(root) for n in names if n.endswith(".py"))
            findings = scan_tree(root)
            for severity, path, line_no, desc, excerpt in findings:
                feedback.pushWarning("{}: {}:{} {}".format(severity, path, line_no, desc))
            feedback.pushInfo("Scanned Python files: {}. Findings: {}.".format(files, len(findings)))
            output = self.parameterAsFileOutput(parameters, self.OUTPUT, context)
            try:
                with open(output, "w", encoding="utf-8") as f:
                    f.write(_html_report(findings, files))
            except OSError as e:
                raise QgsProcessingException("Unable to write audit report: {}".format(e))
            return {self.OUTPUT: output}
else:
    PluginSecurityAuditAlgorithm = None
