#!/usr/bin/env python3
# Generates entiendo_pipeline_test.ipynb.
# Convention: ALL code() calls use triple-single-quote strings as outer
# wrapper so inner triple-double-quote strings (TypeScript content, prompts,
# raw regex) are never misread as terminators.
import json, textwrap
from pathlib import Path

cells = []

def md(text: str) -> dict:
    lines = textwrap.dedent(text).strip().splitlines(keepends=True)
    return {"cell_type": "markdown", "metadata": {}, "source": lines}

def code(text: str) -> dict:
    text = textwrap.dedent(text).strip()
    lines = text.splitlines(keepends=False)
    source = [l + "\n" for l in lines[:-1]] + ([lines[-1]] if lines else [])
    return {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": source,
    }

# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 0 – Title & Setup
# ═══════════════════════════════════════════════════════════════════════════════

cells.append(md("""
# Entiendo Pipeline — Complete Test Suite

This notebook walks through **every component** of the Entiendo TypeScript
codebase in Python, from file-tree walking to LangGraph orchestration.

| # | Section | What it tests |
|---|---------|---------------|
| 0 | Setup | Package install, Gemini API smoke-test |
| 1 | Sample project | Creates a realistic multi-file TypeScript repo |
| 2 | File tree | `getFileTree()` equivalent |
| 3 | Knowledge-graph indexer | Import / symbol / edge parsing + Mermaid generation |
| 4 | RAG indexer | Gemini embeddings + Qdrant in-memory + semantic retrieval |
| 5 | Intent router | Entry node with Gemini structured output |
| 6 | Pipeline nodes | All six nodes: macro, micro, diagram, deep, refactor, test |
| 7 | LangGraph | Full graph wired and run end-to-end |
| 8 | Socket.io client | Smoke-test against the running server |

> **Prerequisite** — `GEMINI_API_KEY` in your environment or `.env` file.
"""))

cells.append(code('''
import subprocess, sys

pkgs = [
    "google-generativeai",
    "langchain-google-genai",
    "langgraph",
    "qdrant-client",
    "networkx",
    "matplotlib",
    "numpy",
    "python-dotenv",
    "python-socketio[client]",
    "pydantic",
]
subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", *pkgs])
print("All packages installed.")
'''))

cells.append(code('''
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path.cwd() / ".env")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    # Uncomment for Google Colab:
    # from google.colab import userdata
    # GEMINI_API_KEY = userdata.get("GEMINI_API_KEY")
    raise ValueError("Set GEMINI_API_KEY in your environment or .env file")

print(f"API key present: {GEMINI_API_KEY[:8]}...")

import google.generativeai as genai
genai.configure(api_key=GEMINI_API_KEY)

_r = genai.GenerativeModel("gemini-1.5-flash").generate_content("Say only: ENTIENDO READY")
print(_r.text.strip())
'''))

# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 1 – Sample TypeScript project
# ═══════════════════════════════════════════════════════════════════════════════

cells.append(md("""
## 1  Sample TypeScript Project

We write a realistic multi-file Node.js / TypeScript app to disk so every
subsequent section has real code to parse, index, and query.

```
/tmp/entiendo_sample/
  src/
    app.ts           ← App class – wires Database, AuthService, Router
    auth.ts          ← AuthService – login / register / verifyToken
    database.ts      ← Database class – findUser / createUser / query
    routes.ts        ← Router – HTTP handler delegates to AuthService
    utils.ts         ← hashPassword / generateToken / Logger
    models/user.ts   ← User interface + UserModel class
  package.json
  tsconfig.json
```
"""))

# Each TS file is stored in the cell code as a """...""" string (safe because
# the outer code() wrapper uses ''' so """ is just regular content).
cells.append(code('''
import json, re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

PROJECT_DIR = Path("/tmp/entiendo_sample")
PROJECT_DIR.mkdir(exist_ok=True)

FILES: Dict[str, str] = {}

FILES["src/app.ts"] = """
import { createServer } from 'http';
import { Router } from './routes';
import { AuthService } from './auth';
import { Database } from './database';
import { Logger } from './utils';

export class App {
  private router: Router;
  private auth: AuthService;
  private db: Database;

  constructor() {
    this.db     = new Database();
    this.auth   = new AuthService(this.db);
    this.router = new Router(this.auth);
  }

  start(port: number): void {
    const server = createServer(this.router.handle.bind(this.router));
    server.listen(port, () => { Logger.info(`Server on port ${port}`); });
  }
}

const app = new App();
app.start(3000);
""".strip()

FILES["src/auth.ts"] = """
import { Database } from './database';
import { hashPassword, generateToken, parseToken } from './utils';
import { User } from './models/user';

export class AuthService {
  constructor(private db: Database) {}

  async login(email: string, password: string): Promise<string> {
    const user = await this.db.findUser(email);
    if (!user) throw new Error('User not found');
    if (user.passwordHash !== hashPassword(password)) throw new Error('Bad password');
    return generateToken(user.id);
  }

  async register(email: string, password: string): Promise<User> {
    if (await this.db.findUser(email)) throw new Error('Already exists');
    return this.db.createUser({ email, passwordHash: hashPassword(password) });
  }

  async verifyToken(token: string): Promise<User | null> {
    try { return this.db.findUserById(parseToken(token)); }
    catch { return null; }
  }
}
""".strip()

FILES["src/database.ts"] = """
import { User } from './models/user';
import { Logger } from './utils';

export interface QueryResult<T> { data: T; count: number; }

export class Database {
  async connect(url: string): Promise<void> { Logger.info(`Connecting: ${url}`); }
  async findUser(email: string): Promise<User | null> { return null; }
  async findUserById(id: string): Promise<User | null> { return null; }
  async createUser(data: Partial<User>): Promise<User> {
    return { id: 'gen-id', ...data } as User;
  }
  async query<T>(sql: string, params: unknown[]): Promise<QueryResult<T>> {
    return { data: [] as T, count: 0 };
  }
}
""".strip()

FILES["src/routes.ts"] = """
import { AuthService } from './auth';
import { IncomingMessage, ServerResponse } from 'http';
import { Logger } from './utils';

export class Router {
  constructor(private auth: AuthService) {}

  async handle(req: IncomingMessage, res: ServerResponse): Promise<void> {
    const url = req.url || '/';
    Logger.info(`${req.method} ${url}`);
    try {
      if (url === '/auth/login'    && req.method === 'POST') await this.handleLogin(req, res);
      else if (url === '/auth/register' && req.method === 'POST') await this.handleRegister(req, res);
      else this.send(res, 404, { error: 'Not found' });
    } catch { this.send(res, 500, { error: 'Server error' }); }
  }

  private async handleLogin(req: IncomingMessage, res: ServerResponse) {
    const { email, password } = await this.parseBody(req);
    this.send(res, 200, { token: await this.auth.login(email, password) });
  }

  private async handleRegister(req: IncomingMessage, res: ServerResponse) {
    const { email, password } = await this.parseBody(req);
    this.send(res, 201, { user: await this.auth.register(email, password) });
  }

  private send(res: ServerResponse, status: number, data: unknown): void {
    res.writeHead(status, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify(data));
  }

  private parseBody(req: IncomingMessage): Promise<Record<string, string>> {
    return new Promise(resolve => {
      let body = '';
      req.on('data', c => (body += c));
      req.on('end', () => resolve(JSON.parse(body)));
    });
  }
}
""".strip()

FILES["src/utils.ts"] = """
import crypto from 'crypto';

const JWT_SECRET = process.env.JWT_SECRET || 'dev-secret';

export function hashPassword(pw: string): string {
  return crypto.createHash('sha256').update(pw).digest('hex');
}

export function generateToken(userId: string): string {
  return Buffer.from(JSON.stringify({ userId, exp: Date.now() + 7*86400*1000 })).toString('base64');
}

export function parseToken(token: string): string {
  const p = JSON.parse(Buffer.from(token, 'base64').toString());
  if (p.exp < Date.now()) throw new Error('Expired');
  return p.userId;
}

export class Logger {
  static info(msg: string)  { console.log(`[INFO]  ${new Date().toISOString()} ${msg}`); }
  static error(msg: string) { console.error(`[ERROR] ${new Date().toISOString()} ${msg}`); }
}
""".strip()

FILES["src/models/user.ts"] = """
export interface User {
  id: string;
  email: string;
  passwordHash: string;
  createdAt: Date;
  updatedAt: Date;
}

export class UserModel implements User {
  id: string; email: string; passwordHash: string;
  createdAt: Date; updatedAt: Date;

  constructor(d: Partial<User>) {
    this.id           = d.id           || '';
    this.email        = d.email        || '';
    this.passwordHash = d.passwordHash || '';
    this.createdAt    = d.createdAt    || new Date();
    this.updatedAt    = d.updatedAt    || new Date();
  }

  toJSON() { return { id: this.id, email: this.email }; }
}
""".strip()

FILES["package.json"] = json.dumps({
    "name": "sample-app", "version": "1.0.0", "type": "module",
    "scripts": {"dev": "tsx src/app.ts", "test": "vitest run"},
    "devDependencies": {"vitest": "^3.0.0", "tsx": "^4.0.0", "@types/node": "^22.0.0"},
}, indent=2)

FILES["tsconfig.json"] = json.dumps({
    "compilerOptions": {"target": "ES2022", "module": "NodeNext", "strict": True},
}, indent=2)

for rel, content in FILES.items():
    p = PROJECT_DIR / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)

print(f"Created {len(FILES)} files in {PROJECT_DIR}")
for p in sorted(FILES):
    print(f"  {p}")
'''))

# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 2 – File Tree
# ═══════════════════════════════════════════════════════════════════════════════

cells.append(md("""
## 2  File-Tree Exploration

Mirrors `getFileTree()` in `server.ts`.  The server calls this right after
cloning and emits the result as the `repo_structure` Socket.io event.
"""))

cells.append(code('''
SKIP_DIRS = {"node_modules", ".git", "dist", "__pycache__", ".next", "build"}

def get_file_tree(root: Path, base: Path = None) -> List[Dict]:
    if base is None:
        base = root
    results = []
    for item in sorted(root.iterdir()):
        if item.is_dir():
            if item.name not in SKIP_DIRS:
                results.extend(get_file_tree(item, base))
        else:
            results.append({
                "name": item.name,
                "path": str(item.relative_to(base)),
                "size": item.stat().st_size,
            })
    return results

tree = get_file_tree(PROJECT_DIR)
print(f"{'File':<40} {'Bytes':>8}")
print("-" * 50)
for f in tree:
    print(f"{f['path']:<40} {f['size']:>8}")
print(f"\\nTotal files: {len(tree)}")
'''))

# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 3 – Knowledge-Graph Indexer
# ═══════════════════════════════════════════════════════════════════════════════

cells.append(md("""
## 3  Knowledge-Graph Indexer

Python equivalent of `src/tools/graph_indexer.ts`.

The indexer builds a **directed graph** where:
- **Nodes**: files, functions, classes, interfaces, consts
- **Edges**: `imports`, `defines`, `extends`

It powers the `diagram`, `deep_explanation`, `refactor`, and `test` nodes.
"""))

cells.append(code('''
from dataclasses import dataclass, field
from collections import Counter

CODE_EXTS = {".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".py"}


@dataclass
class GNode:
    id: str
    type: str        # file | function | class | interface | const
    file: str
    name: str
    exported: bool = False


@dataclass
class GEdge:
    from_id: str
    to_id: str
    type: str        # imports | defines | extends


@dataclass
class RepoGraph:
    nodes:     Dict[str, GNode]          = field(default_factory=dict)
    edges:     List[GEdge]               = field(default_factory=list)
    in_edges:  Dict[str, List[GEdge]]    = field(default_factory=dict)
    out_edges: Dict[str, List[GEdge]]    = field(default_factory=dict)


def _file_id(rel_path: str) -> str:
    return re.sub(r"[^\\w]", "_", rel_path)


# ── TypeScript / JavaScript parser ────────────────────────────────────────────

def _parse_ts(content: str, rel: str) -> Tuple[List[GNode], List[GEdge]]:
    nodes, edges = [], []
    fid = _file_id(rel)
    nodes.append(GNode(id=fid, type="file", file=rel, name=rel))

    # relative imports:  from './foo'  or  import './side-effect'
    for m in re.finditer(r"""from\\s+['"](\\.[^'"]+)['"]""", content):
        edges.append(GEdge(from_id=fid, to_id=m.group(1), type="imports"))
    for m in re.finditer(r"""^import\\s+['"](\\.[^'"]+)['"]""", content, re.M):
        edges.append(GEdge(from_id=fid, to_id=m.group(1), type="imports"))

    # exported functions
    for m in re.finditer(r"export\\s+(?:async\\s+)?function\\s+(\\w+)", content):
        sid = f"{fid}::{m.group(1)}"
        nodes.append(GNode(id=sid, type="function", file=rel, name=m.group(1), exported=True))
        edges.append(GEdge(from_id=fid, to_id=sid, type="defines"))

    # exported classes (with optional extends)
    for m in re.finditer(r"export\\s+class\\s+(\\w+)(?:\\s+extends\\s+(\\w+))?", content):
        sid = f"{fid}::{m.group(1)}"
        nodes.append(GNode(id=sid, type="class", file=rel, name=m.group(1), exported=True))
        edges.append(GEdge(from_id=fid, to_id=sid, type="defines"))
        if m.group(2):
            edges.append(GEdge(from_id=sid, to_id=m.group(2), type="extends"))

    # exported interfaces
    for m in re.finditer(r"export\\s+interface\\s+(\\w+)", content):
        sid = f"{fid}::{m.group(1)}"
        nodes.append(GNode(id=sid, type="interface", file=rel, name=m.group(1), exported=True))
        edges.append(GEdge(from_id=fid, to_id=sid, type="defines"))

    # exported consts
    for m in re.finditer(r"export\\s+const\\s+(\\w+)", content):
        sid = f"{fid}::{m.group(1)}"
        nodes.append(GNode(id=sid, type="const", file=rel, name=m.group(1), exported=True))
        edges.append(GEdge(from_id=fid, to_id=sid, type="defines"))

    return nodes, edges


# ── Python parser ─────────────────────────────────────────────────────────────

def _parse_py(content: str, rel: str) -> Tuple[List[GNode], List[GEdge]]:
    nodes, edges = [], []
    fid = _file_id(rel)
    nodes.append(GNode(id=fid, type="file", file=rel, name=rel))
    for m in re.finditer(r"from\\s+(\\.\\.?\\w*)\\s+import", content):
        edges.append(GEdge(from_id=fid, to_id=m.group(1), type="imports"))
    for m in re.finditer(r"^def\\s+(\\w+)", content, re.M):
        sid = f"{fid}::{m.group(1)}"
        nodes.append(GNode(id=sid, type="function", file=rel, name=m.group(1),
                           exported=not m.group(1).startswith("_")))
        edges.append(GEdge(from_id=fid, to_id=sid, type="defines"))
    for m in re.finditer(r"^class\\s+(\\w+)(?:\\((\\w+)\\))?", content, re.M):
        sid = f"{fid}::{m.group(1)}"
        nodes.append(GNode(id=sid, type="class", file=rel, name=m.group(1), exported=True))
        edges.append(GEdge(from_id=fid, to_id=sid, type="defines"))
        if m.group(2):
            edges.append(GEdge(from_id=sid, to_id=m.group(2), type="extends"))
    return nodes, edges


print("GNode, GEdge, RepoGraph, parsers defined.")
'''))

cells.append(code('''
class GraphIndexer:
    def __init__(self):
        self._graphs: Dict[str, RepoGraph] = {}

    # ── Indexing ──────────────────────────────────────────────────────────────

    def index_repo(self, repo_path: str, session_id: str, on_progress=None) -> RepoGraph:
        g = RepoGraph()
        root = Path(repo_path)
        all_nodes: List[GNode] = []
        all_edges: List[GEdge] = []

        for fp in sorted(root.rglob("*")):
            if fp.is_dir() or any(s in fp.parts for s in SKIP_DIRS):
                continue
            if fp.suffix not in CODE_EXTS:
                continue
            rel = str(fp.relative_to(root))
            content = fp.read_text(errors="ignore")
            if on_progress:
                on_progress(f"  graph: {rel}")
            ns, es = (_parse_ts(content, rel) if fp.suffix in {".ts",".tsx",".js",".jsx",".mjs"}
                      else _parse_py(content, rel) if fp.suffix == ".py"
                      else ([], []))
            all_nodes.extend(ns)
            all_edges.extend(es)

        for n in all_nodes:
            g.nodes[n.id] = n

        # Resolve relative import edges → actual file IDs
        for e in all_edges:
            if e.type != "imports":
                g.edges.append(e)
                continue
            from_node = g.nodes.get(e.from_id)
            if not from_node:
                continue
            from_dir = Path(from_node.file).parent
            base = str((from_dir / e.to_id))
            resolved = next(
                (_file_id(base + suf) for suf in
                 ["", ".ts", ".tsx", ".js", "/index.ts", "/index.js"]
                 if _file_id(base + suf) in g.nodes),
                None,
            )
            if resolved:
                g.edges.append(GEdge(from_id=e.from_id, to_id=resolved, type="imports"))

        for e in g.edges:
            g.out_edges.setdefault(e.from_id, []).append(e)
            g.in_edges.setdefault(e.to_id,   []).append(e)

        self._graphs[session_id] = g
        return g

    # ── Mermaid generators ────────────────────────────────────────────────────

    def to_mermaid(self, sid: str, root_files: List[str] = None) -> Optional[str]:
        g = self._graphs.get(sid)
        if not g:
            return None
        file_ids = {nid for nid, n in g.nodes.items() if n.type == "file"}
        if not root_files:
            scores = {
                fid: len(g.in_edges.get(fid, [])) + len(g.out_edges.get(fid, []))
                for fid in file_ids
            }
            target_ids = set(sorted(scores, key=scores.get, reverse=True)[:25])
        else:
            target_ids = {_file_id(f) for f in root_files}

        lines = ["flowchart LR"]
        for nid in target_ids:
            n = g.nodes.get(nid)
            if n:
                label = Path(n.file).stem
                lines.append(f\'  {nid}["{label}"]\')

        seen: set = set()
        for e in g.edges:
            if e.type == "imports" and e.from_id in target_ids and e.to_id in target_ids:
                k = (e.from_id, e.to_id)
                if k not in seen:
                    seen.add(k)
                    lines.append(f"  {e.from_id} --> {e.to_id}")
        return "\\n".join(lines) if seen else None

    def to_class_diagram(self, sid: str) -> Optional[str]:
        g = self._graphs.get(sid)
        if not g:
            return None
        lines = ["classDiagram"]
        has = False
        for e in g.edges:
            if e.type == "extends":
                fn = g.nodes.get(e.from_id)
                if fn:
                    lines.append(f"  {e.to_id} <|-- {fn.name}")
                    has = True
        for nid, n in g.nodes.items():
            if n.type == "class":
                members = [
                    g.nodes[e.to_id].name
                    for e in g.out_edges.get(nid, [])
                    if e.type == "defines" and e.to_id in g.nodes
                ]
                if members:
                    lines.append(f"  class {n.name} {{")
                    for m in members[:5]:
                        lines.append(f"    +{m}()")
                    lines.append("  }")
                    has = True
        return "\\n".join(lines) if has else None

    # ── Context queries ───────────────────────────────────────────────────────

    def get_file_context(self, file_path: str, sid: str) -> str:
        g = self._graphs.get(sid)
        if not g:
            return ""
        fid = _file_id(file_path)
        n = g.nodes.get(fid)
        if not n:
            return f"'{file_path}' not found in graph."
        exports = [
            g.nodes[e.to_id].name for e in g.out_edges.get(fid, [])
            if e.type == "defines" and e.to_id in g.nodes
        ]
        imports = [
            g.nodes[e.to_id].file for e in g.out_edges.get(fid, [])
            if e.type == "imports" and e.to_id in g.nodes
        ]
        imported_by = [
            g.nodes[e.from_id].file for e in g.in_edges.get(fid, [])
            if e.type == "imports" and e.from_id in g.nodes
        ]
        return (
            f"File       : {file_path}\\n"
            f"Exports    : {', '.join(exports) or 'none'}\\n"
            f"Imports    : {', '.join(imports) or 'none'}\\n"
            f"Imported by: {', '.join(imported_by) or 'none'}\\n"
            f"Impact     : {len(imported_by)} direct dependents"
        )

    def get_context_for_query(self, query: str, sid: str) -> str:
        g = self._graphs.get(sid)
        if not g:
            return ""
        words = query.lower().split()
        hits = [n for n in g.nodes.values()
                if n.type != "file" and any(w in n.name.lower() for w in words)]
        if not hits:
            return self.get_summary(sid)
        seen_files: set = set()
        parts: List[str] = []
        for h in hits[:5]:
            if h.file not in seen_files:
                seen_files.add(h.file)
                parts.append(self.get_file_context(h.file, sid))
        return "\\n\\n".join(parts)

    def get_summary(self, sid: str) -> str:
        g = self._graphs.get(sid)
        if not g:
            return "No graph."
        files   = sum(1 for n in g.nodes.values() if n.type == "file")
        symbols = sum(1 for n in g.nodes.values() if n.type != "file")
        ic: Dict[str, int] = {}
        for e in g.edges:
            if e.type == "imports" and e.to_id in g.nodes:
                f = g.nodes[e.to_id].file
                ic[f] = ic.get(f, 0) + 1
        top = sorted(ic, key=ic.get, reverse=True)[:3]  # type: ignore[arg-type]
        return (
            f"Files: {files}  Symbols: {symbols}  Edges: {len(g.edges)}\\n"
            f"Most-imported: {', '.join(top) or 'none'}"
        )

print("GraphIndexer defined.")
'''))

cells.append(code('''
SESSION_ID = "notebook_session"
REPO_PATH  = str(PROJECT_DIR)

graph_indexer = GraphIndexer()
g = graph_indexer.index_repo(REPO_PATH, SESSION_ID, on_progress=print)

print()
print("=" * 52)
print(graph_indexer.get_summary(SESSION_ID))
print()

# Node type breakdown
counts = Counter(n.type for n in g.nodes.values())
print("Node types:")
for t, c in sorted(counts.items()):
    print(f"  {t:<15} {c}")

print()
print(f"{'from':<36} {'type':<12} {'to'}")
print(f"  {'-'*34} {'-'*10} {'-'*34}")
for e in g.edges[:15]:
    fn = g.nodes.get(e.from_id)
    tn = g.nodes.get(e.to_id)
    fname = fn.name if fn else e.from_id
    tname = tn.name if tn else e.to_id
    print(f"  {fname:<34} {e.type:<12} {tname}")
'''))

cells.append(code('''
import networkx as nx
import matplotlib.pyplot as plt

G = nx.DiGraph()
file_nodes = {nid: n for nid, n in g.nodes.items() if n.type == "file"}
for nid in file_nodes:
    G.add_node(nid)
for e in g.edges:
    if e.type == "imports" and e.from_id in file_nodes and e.to_id in file_nodes:
        G.add_edge(e.from_id, e.to_id)

labels = {nid: Path(n.file).stem for nid, n in file_nodes.items() if G.has_node(nid)}

plt.figure(figsize=(10, 7))
pos = nx.spring_layout(G, seed=42, k=2.5)
nx.draw_networkx_nodes(G, pos, node_size=2200, node_color="#4f86c6", alpha=0.92)
nx.draw_networkx_labels(G, pos, labels, font_size=8, font_color="white", font_weight="bold")
nx.draw_networkx_edges(G, pos, arrowsize=18, width=1.5,
                       edge_color="#444", arrows=True,
                       connectionstyle="arc3,rad=0.1")
plt.title("File Dependency Graph — entiendo_sample", fontsize=13)
plt.axis("off")
plt.tight_layout()
plt.show()
print(f"Nodes: {G.number_of_nodes()}  Edges: {G.number_of_edges()}")
'''))

cells.append(code('''
print("── Mermaid: Dependency flowchart ───────────────────────────────────")
mermaid_dep = graph_indexer.to_mermaid(SESSION_ID)
print(mermaid_dep or "(no diagram – not enough resolved import edges)")

print()
print("── Mermaid: Class diagram ──────────────────────────────────────────")
mermaid_cls = graph_indexer.to_class_diagram(SESSION_ID)
print(mermaid_cls or "(no classes with extends)")

print()
print("── File context: src/auth.ts ───────────────────────────────────────")
print(graph_indexer.get_file_context("src/auth.ts", SESSION_ID))

print()
print("── File context: src/database.ts ───────────────────────────────────")
print(graph_indexer.get_file_context("src/database.ts", SESSION_ID))

print()
print("── Context for query: authentication login token ───────────────────")
print(graph_indexer.get_context_for_query("authentication login token", SESSION_ID))
'''))

# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 4 – RAG Indexer
# ═══════════════════════════════════════════════════════════════════════════════

cells.append(md("""
## 4  RAG Indexer

Python equivalent of `src/tools/rag_indexer.ts`.

**Pipeline:**

1. **Chunk** every source file on double-newlines
2. **Embed** via Gemini `text-embedding-004` (768-dim)
3. **Store** in Qdrant in-memory (auto-fallback to plain Python dict)
4. **Retrieve** top-K by cosine similarity for any query
"""))

cells.append(code('''
import numpy as np

CODE_EXTS_RAG   = {".ts", ".tsx", ".js", ".jsx", ".py", ".mjs", ".json", ".md"}
MAX_FILES_RAG   = 60
MAX_CHUNK_CHARS = 2048


def chunk_file(content: str, file_path: str) -> List[Dict[str, Any]]:
    """Split on double-newlines; drop tiny chunks (mirrors TS chunkFile)."""
    chunks = []
    for i, raw in enumerate(re.split(r"\\n{2,}", content)):
        raw = raw.strip()
        if len(raw) >= 30:
            chunks.append({"text": raw[:MAX_CHUNK_CHARS], "file": file_path, "idx": i})
    return chunks


def embed_texts(texts: List[str]) -> List[List[float]]:
    """Embed using Gemini text-embedding-004 (768 dims)."""
    return [
        genai.embed_content(
            model="models/text-embedding-004",
            content=t[:2048],
            task_type="retrieval_document",
        )["embedding"]
        for t in texts
    ]


def cosine_sim(a: List[float], b: List[float]) -> float:
    va, vb = np.array(a), np.array(b)
    d = np.linalg.norm(va) * np.linalg.norm(vb)
    return float(np.dot(va, vb) / d) if d > 0 else 0.0


# Smoke-test embedding
probe = embed_texts(["authentication flow in Node.js"])[0]
print(f"Embedding dimension: {len(probe)}  (expected 768)")
'''))

cells.append(code('''
class RagIndexer:
    def __init__(self):
        self._mem: Dict[str, List[Dict]] = {}
        self._qdrant = None
        try:
            from qdrant_client import QdrantClient
            from qdrant_client.models import Distance, VectorParams
            self._qdrant = QdrantClient(":memory:")
            self._Distance     = Distance
            self._VectorParams = VectorParams
            print("Qdrant in-memory client ready.")
        except Exception as exc:
            print(f"Qdrant unavailable ({exc}) — using dict fallback.")

    def _col(self, sid: str) -> str:
        return "nb_" + re.sub(r"[^\\w]", "_", sid)[:30]

    def index_repo(self, repo_path: str, sid: str, on_progress=None) -> int:
        root   = Path(repo_path)
        files  = [
            fp for fp in sorted(root.rglob("*"))
            if fp.is_file() and fp.suffix in CODE_EXTS_RAG
            and not any(s in fp.parts for s in SKIP_DIRS)
        ][:MAX_FILES_RAG]

        all_chunks: List[Dict] = []
        for fp in files:
            rel = str(fp.relative_to(root))
            if on_progress:
                on_progress(f"  rag: chunk {rel}")
            try:
                all_chunks.extend(chunk_file(fp.read_text(errors="ignore"), rel))
            except Exception as exc:
                print(f"    skip {rel}: {exc}")

        if not all_chunks:
            return 0

        if on_progress:
            on_progress(f"  rag: embedding {len(all_chunks)} chunks…")
        embs = embed_texts([c["text"] for c in all_chunks])
        for c, e in zip(all_chunks, embs):
            c["embedding"] = e

        if self._qdrant:
            from qdrant_client.models import PointStruct
            col = self._col(sid)
            try:
                self._qdrant.delete_collection(col)
            except Exception:
                pass
            self._qdrant.create_collection(
                col,
                vectors_config=self._VectorParams(size=768, distance=self._Distance.COSINE),
            )
            self._qdrant.upsert(col, points=[
                PointStruct(id=i, vector=c["embedding"],
                            payload={"text": c["text"], "file": c["file"]})
                for i, c in enumerate(all_chunks)
            ])
            if on_progress:
                on_progress(f"  rag: stored {len(all_chunks)} chunks in Qdrant")
        else:
            self._mem[sid] = all_chunks
            if on_progress:
                on_progress(f"  rag: stored {len(all_chunks)} chunks in-memory")

        return len(all_chunks)

    def retrieve(self, query: str, sid: str, top_k: int = 5) -> List[Dict]:
        q_emb = embed_texts([query])[0]

        if self._qdrant:
            try:
                hits = self._qdrant.search(self._col(sid), q_emb, limit=top_k, score_threshold=0.4)
                return [{"text": h.payload["text"], "file": h.payload["file"], "score": h.score}
                        for h in hits]
            except Exception as exc:
                print(f"Qdrant search error ({exc}), falling back to dict.")

        chunks = self._mem.get(sid, [])
        scored = sorted(
            ({**c, "score": cosine_sim(q_emb, c["embedding"])} for c in chunks if "embedding" in c),
            key=lambda x: x["score"], reverse=True,
        )
        return [{"text": s["text"], "file": s["file"], "score": s["score"]}
                for s in scored[:top_k] if s["score"] > 0.4]

print("RagIndexer defined.")
'''))

cells.append(code('''
rag_indexer = RagIndexer()
n = rag_indexer.index_repo(REPO_PATH, SESSION_ID, on_progress=print)
print(f"\\nTotal chunks indexed: {n}")

TEST_QUERIES = [
    "How does user authentication work?",
    "Where is the token generated and validated?",
    "How are HTTP routes handled and dispatched?",
]

for q in TEST_QUERIES:
    print(f"\\n[Query] {q!r}")
    for r in rag_indexer.retrieve(q, SESSION_ID, top_k=3):
        preview = r["text"][:100].replace("\\n", " ")
        print(f"  score={r['score']:.3f}  file={r['file']}  → {preview}…")
'''))

# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 5 – Intent Router (entry node)
# ═══════════════════════════════════════════════════════════════════════════════

cells.append(md("""
## 5  Intent Classification — Entry Node

Python equivalent of the `entry` node in `src/orchestration/graph.ts`.

Gemini is called with **structured output** (Pydantic schema) and returns one
of seven intents plus the target files.

| Intent | Triggered by |
|--------|-------------|
| `macro_structure` | "how does this project work?" |
| `micro_logic` | "walk through the login function" |
| `diagram` | "show the dependency diagram" |
| `deep_explanation` | "explain how token verification works" |
| `refactor` | "refactor auth.ts" |
| `test` | "write unit tests for Router" |
| `error` | ambiguous / off-topic |
"""))

cells.append(code('''
from typing import Literal, TypedDict
from pydantic import BaseModel, Field
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import StateGraph, START, END


class AgentState(TypedDict):
    session_id:           str
    user_query:           str
    repo_path:            str
    intent:               str
    target_files:         List[str]
    conversation_history: str          # JSON: [{role, content}]
    git_diff:             Optional[str]
    output_type:          Optional[str] # mermaid | markdown | diff_proposal
    output_ref:           Optional[str] # actual content
    error:                Optional[str]


class RouterSchema(BaseModel):
    intent: Literal[
        "macro_structure", "micro_logic", "diagram",
        "deep_explanation", "refactor", "test", "error"
    ] = Field(description="Type of analysis requested")
    target_files: List[str] = Field(
        default_factory=list,
        description="Specific files mentioned or strongly implied",
    )
    confidence: float = Field(ge=0.0, le=1.0)


llm_standard = ChatGoogleGenerativeAI(
    model="gemini-1.5-flash", temperature=0, google_api_key=GEMINI_API_KEY
)
llm_complex = ChatGoogleGenerativeAI(
    model="gemini-1.5-pro", temperature=0.1, google_api_key=GEMINI_API_KEY
)
print("AgentState, RouterSchema, LLM instances ready.")
'''))

cells.append(code('''
ROUTER_SYSTEM = """
You are a code-analysis router. Classify the user query into exactly ONE intent:
  macro_structure  — high-level architecture, how modules connect, project overview
  micro_logic      — logic flow inside a specific file or function
  diagram          — generate a dependency / class / flowchart diagram
  deep_explanation — in-depth technical explanation; needs codebase search
  refactor         — suggest or apply code improvements
  test             — generate unit tests
  error            — query is unclear or off-topic

Also extract target_files if any files are clearly mentioned or implied.
""".strip()


def entry_node(state: AgentState) -> AgentState:
    history = json.loads(state.get("conversation_history") or "[]")
    hist_txt = "\\n".join(f"{m['role'].upper()}: {m['content']}" for m in history[-6:]) or "None"
    sllm = llm_standard.with_structured_output(RouterSchema)
    result: RouterSchema = sllm.invoke([
        SystemMessage(content=ROUTER_SYSTEM),
        HumanMessage(content=f"Conversation:\\n{hist_txt}\\n\\nQuery: {state['user_query']}"),
    ])
    return {**state, "intent": result.intent, "target_files": result.target_files}


def route_by_intent(state: AgentState) -> str:
    return state["intent"]


# ── Test the router with 6 representative queries ─────────────────────────────

test_queries = [
    "Give me a high-level overview of this codebase",
    "Show the file dependency diagram",
    "Walk me through the login flow step by step in auth.ts",
    "How does the AuthService verify tokens?",
    "Refactor utils.ts to use proper error classes",
    "Write vitest unit tests for the AuthService",
]

print(f"{'Query':<57} {'Intent':<20} Conf")
print("-" * 85)
sllm = llm_standard.with_structured_output(RouterSchema)
for q in test_queries:
    r: RouterSchema = sllm.invoke([
        SystemMessage(content=ROUTER_SYSTEM),
        HumanMessage(content=f"Query: {q}"),
    ])
    print(f"{q:<57} {r.intent:<20} {r.confidence:.2f}")
'''))

# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 6 – Pipeline Nodes
# ═══════════════════════════════════════════════════════════════════════════════

cells.append(md("""
## 6  Pipeline Nodes

Each cell implements one LangGraph node and runs a quick smoke-test.

The TypeScript nodes stream tokens via `tokenEmitter` → Socket.io.
In Python we just collect the full response and print it.
"""))

# macro + micro
cells.append(code('''
# ── macro_structure ───────────────────────────────────────────────────────────

def macro_structure_node(state: AgentState) -> AgentState:
    root    = Path(state["repo_path"])
    listing = sorted(
        str(fp.relative_to(root))
        for fp in root.rglob("*")
        if fp.is_file() and fp.suffix in CODE_EXTS
        and not any(s in fp.parts for s in SKIP_DIRS)
    )
    summary = graph_indexer.get_summary(state["session_id"])
    mermaid = graph_indexer.to_mermaid(state["session_id"]) or "unavailable"
    history = json.loads(state.get("conversation_history") or "[]")
    hist    = "\\n".join(f"{m['role'].upper()}: {m['content']}" for m in history[-6:]) or "None"

    prompt = f"""Analyse this repository\'s architecture.

Files:
{chr(10).join(listing[:30])}

Graph summary:
{summary}

Dependency graph (Mermaid):
{mermaid}

Conversation history:
{hist}

User query: {state['user_query']}

Respond in well-structured markdown."""

    resp = llm_standard.invoke([HumanMessage(content=prompt)])
    return {**state, "output_type": "markdown", "output_ref": resp.content}


# ── micro_logic ───────────────────────────────────────────────────────────────

def micro_logic_node(state: AgentState) -> AgentState:
    target = state["target_files"][0] if state["target_files"] else None
    if not target:
        for fp in Path(state["repo_path"]).rglob("*.ts"):
            if not any(s in fp.parts for s in SKIP_DIRS):
                target = str(fp.relative_to(Path(state["repo_path"])))
                break
    content = ""
    if target:
        try:
            content = (Path(state["repo_path"]) / target).read_text()[:3000]
        except Exception:
            pass

    prompt = f"""Generate a Mermaid flowchart for the logic in this file.

File: {target or "unknown"}
---
{content}
---
Query: {state["user_query"]}

Return ONLY the raw Mermaid code — no fences, no explanation."""

    raw     = llm_standard.invoke([HumanMessage(content=prompt)]).content.strip()
    mermaid = re.sub(r"^```(?:mermaid)?\\n?", "", raw)
    mermaid = re.sub(r"\\n?```$", "", mermaid)
    return {**state, "output_type": "mermaid", "output_ref": mermaid.strip()}


# ── Smoke tests ───────────────────────────────────────────────────────────────

BASE: AgentState = {
    "session_id": SESSION_ID, "repo_path": REPO_PATH,
    "intent": "macro_structure", "target_files": [],
    "conversation_history": "[]", "git_diff": None,
    "output_type": None, "output_ref": None, "error": None,
    "user_query": "Give me a high-level overview",
}

print("=== macro_structure ===")
r1 = macro_structure_node(BASE)
print(r1["output_ref"][:600], "…")

print("\\n=== micro_logic ===")
r2 = micro_logic_node({**BASE,
    "user_query": "Walk through the authentication logic",
    "target_files": ["src/auth.ts"]})
print(r2["output_ref"][:400], "…")
'''))

# diagram
cells.append(code('''
# ── diagram ───────────────────────────────────────────────────────────────────

def diagram_node(state: AgentState) -> AgentState:
    q       = state["user_query"].lower()
    summary = graph_indexer.get_summary(state["session_id"])

    if any(k in q for k in ("class", "uml", "inherit", "hierarch")):
        m = graph_indexer.to_class_diagram(state["session_id"])
        if m:
            return {**state, "output_type": "mermaid", "output_ref": m}

    if any(k in q for k in ("depend", "import", "architecture", "module", "structure")):
        m = graph_indexer.to_mermaid(state["session_id"])
        if m:
            return {**state, "output_type": "mermaid", "output_ref": m}

    ctx = graph_indexer.to_mermaid(state["session_id"]) or ""
    raw = llm_standard.invoke([HumanMessage(content=(
        f"Generate a Mermaid diagram for: {state['user_query']}\\n\\n"
        f"Graph context:\\n{summary}\\n\\nExisting structure:\\n{ctx}\\n\\n"
        "Return ONLY valid Mermaid code — no fences, no explanation."
    ))]).content.strip()
    mermaid = re.sub(r"^```(?:mermaid)?\\n?", "", raw)
    mermaid = re.sub(r"\\n?```$", "", mermaid)
    return {**state, "output_type": "mermaid", "output_ref": mermaid.strip()}


print("=== diagram — dependency ===")
r3 = diagram_node({**BASE, "user_query": "Show the import dependency diagram"})
print(r3["output_ref"][:500])

print("\\n=== diagram — class ===")
r4 = diagram_node({**BASE, "user_query": "Draw the class hierarchy"})
print(r4["output_ref"][:500])
'''))

# deep_explanation
cells.append(code('''
# ── deep_explanation (RAG + graph fusion) ─────────────────────────────────────

def deep_explanation_node(state: AgentState) -> AgentState:
    hits    = rag_indexer.retrieve(state["user_query"], state["session_id"], top_k=5)
    rag_ctx = "\\n\\n---\\n\\n".join(
        f"[{h['file']}  score={h['score']:.2f}]\\n{h['text']}" for h in hits
    ) or "No matching chunks."

    graph_ctx = (
        "\\n\\n".join(
            graph_indexer.get_file_context(f, state["session_id"])
            for f in state["target_files"][:3]
        )
        if state["target_files"]
        else graph_indexer.get_summary(state["session_id"])
    )
    history = json.loads(state.get("conversation_history") or "[]")
    hist    = "\\n".join(f"{m['role'].upper()}: {m['content']}" for m in history[-6:]) or "None"

    prompt = f"""You are an expert code analyst. Provide a deep technical explanation.

Query: {state["user_query"]}

Relevant code (semantic search):
{rag_ctx}

Knowledge-graph context:
{graph_ctx}

Conversation history:
{hist}

Write a comprehensive, technically accurate explanation in markdown."""

    resp = llm_complex.invoke([HumanMessage(content=prompt)])
    return {**state, "output_type": "markdown", "output_ref": resp.content}


print("=== deep_explanation ===")
r5 = deep_explanation_node({**BASE,
    "user_query": "How does authentication work end-to-end?",
    "target_files": ["src/auth.ts"]})
print(r5["output_ref"][:700], "…")
'''))

# refactor
cells.append(code('''
# ── refactor (SEARCH / REPLACE blocks) ───────────────────────────────────────

def _parse_search_replace(original: str, llm_out: str, file_path: str) -> List[Dict]:
    blocks = re.findall(r"<<<<\\n(.*?)\\n====\\n(.*?)\\n>>>>", llm_out, re.DOTALL)
    diffs, modified = [], original
    for search, replace in blocks:
        if search.strip() in modified:
            modified = modified.replace(search.strip(), replace.strip(), 1)
            diffs.append({"file": file_path, "search": search.strip(),
                          "replace": replace.strip(), "applied": True})
        else:
            diffs.append({"file": file_path, "search": search.strip(),
                          "replace": replace.strip(), "applied": False,
                          "error": "search string not found"})
    return diffs


def refactor_node(state: AgentState) -> AgentState:
    target = state["target_files"][0] if state["target_files"] else None
    if not target:
        return {**state, "output_type": "markdown",
                "output_ref": "Please specify which file to refactor."}
    try:
        content = (Path(state["repo_path"]) / target).read_text()
    except Exception as exc:
        return {**state, "output_type": "markdown", "output_ref": f"Cannot read {target}: {exc}"}

    ctx    = graph_indexer.get_file_context(target, state["session_id"])
    prompt = f"""Refactor the following TypeScript file.

File: {target}
```typescript
{content}
```
Graph context (what imports this file):
{ctx}

Request: {state["user_query"]}

Provide changes as SEARCH/REPLACE blocks:
<<<<
<exact lines from the original>
====
<replacement>
>>>>

After the blocks, add a brief explanation."""

    raw   = llm_complex.invoke([HumanMessage(content=prompt)]).content
    diffs = _parse_search_replace(content, raw, target)
    applied = sum(1 for d in diffs if d["applied"])
    print(f"  Parsed {len(diffs)} block(s), {applied} applied.")
    return {**state, "output_type": "diff_proposal", "output_ref": json.dumps(diffs, indent=2)}


print("=== refactor ===")
r6 = refactor_node({**BASE,
    "user_query": "Add JSDoc comments to all public methods",
    "target_files": ["src/auth.ts"]})
for d in json.loads(r6["output_ref"]):
    status = "APPLIED" if d["applied"] else f"SKIPPED ({d.get('error','')})"
    print(f"  {status}: {d['search'][:60].strip()!r}…")
'''))

# test + error_handler
cells.append(code('''
# ── test ─────────────────────────────────────────────────────────────────────

def test_node(state: AgentState) -> AgentState:
    target = state["target_files"][0] if state["target_files"] else None
    if not target:
        return {**state, "output_type": "markdown",
                "output_ref": "Please specify which file to test."}
    try:
        content = (Path(state["repo_path"]) / target).read_text()
    except Exception as exc:
        return {**state, "output_type": "markdown", "output_ref": f"Cannot read {target}: {exc}"}

    framework = "vitest"
    try:
        pkg  = json.loads((Path(state["repo_path"]) / "package.json").read_text())
        deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
        if "jest"  in deps: framework = "jest"
        elif "mocha" in deps: framework = "mocha"
    except Exception:
        pass

    ctx    = graph_indexer.get_file_context(target, state["session_id"])
    prompt = f"""Generate comprehensive unit tests using {framework}.

File under test: {target}
```typescript
{content}
```
Graph context (for mocking):
{ctx}

Request: {state["user_query"]}

Requirements:
- {framework} + TypeScript syntax
- Mock all external dependencies
- Test happy path AND edge/error cases
- Use describe / it blocks with clear names

Return the complete, runnable test file."""

    resp = llm_complex.invoke([HumanMessage(content=prompt)])
    return {**state, "output_type": "markdown", "output_ref": resp.content}


# ── error_handler ─────────────────────────────────────────────────────────────

def error_handler_node(state: AgentState) -> AgentState:
    return {**state, "output_type": "markdown",
            "output_ref": "I could not understand your query. Could you clarify what you need?"}


print("=== test ===")
r7 = test_node({**BASE,
    "user_query": "Write unit tests for all public methods of AuthService",
    "target_files": ["src/auth.ts"]})
print(r7["output_ref"][:700], "…")
'''))

# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 7 – LangGraph
# ═══════════════════════════════════════════════════════════════════════════════

cells.append(md("""
## 7  Full LangGraph Orchestration

Same topology as `src/orchestration/graph.ts`:

```
START → entry → [conditional on intent] → {node} → END
```
"""))

cells.append(code('''
builder = StateGraph(AgentState)

for name, fn in [
    ("entry",           entry_node),
    ("macro_structure", macro_structure_node),
    ("micro_logic",     micro_logic_node),
    ("diagram",         diagram_node),
    ("deep_explanation",deep_explanation_node),
    ("refactor",        refactor_node),
    ("test",            test_node),
    ("error_handler",   error_handler_node),
]:
    builder.add_node(name, fn)

builder.add_edge(START, "entry")
builder.add_conditional_edges(
    "entry",
    route_by_intent,
    {
        "macro_structure":  "macro_structure",
        "micro_logic":      "micro_logic",
        "diagram":          "diagram",
        "deep_explanation": "deep_explanation",
        "refactor":         "refactor",
        "test":             "test",
        "error":            "error_handler",
    },
)
for node_name in [
    "macro_structure", "micro_logic", "diagram",
    "deep_explanation", "refactor", "test", "error_handler",
]:
    builder.add_edge(node_name, END)

entiendo_graph = builder.compile()
print("Graph compiled. Nodes:", list(entiendo_graph.nodes))
'''))

cells.append(code('''
# Render the graph topology (requires graphviz; falls back to Mermaid source)
try:
    from IPython.display import Image, display
    display(Image(entiendo_graph.get_graph().draw_mermaid_png()))
    print("Graph rendered above.")
except Exception as exc:
    print(f"Graphviz unavailable ({exc}).  Mermaid source:")
    print(entiendo_graph.get_graph().draw_mermaid())
'''))

cells.append(code('''
# ── End-to-end runs ───────────────────────────────────────────────────────────

CONVERSATION: List[Dict] = []

def run(query: str, files: List[str] = None) -> AgentState:
    state: AgentState = {
        "session_id":           SESSION_ID,
        "user_query":           query,
        "repo_path":            REPO_PATH,
        "intent":               "error",
        "target_files":         files or [],
        "conversation_history": json.dumps(CONVERSATION[-10:]),
        "git_diff":             None,
        "output_type":          None,
        "output_ref":           None,
        "error":                None,
    }
    result = entiendo_graph.invoke(state)
    CONVERSATION.append({"role": "user",      "content": query})
    CONVERSATION.append({"role": "assistant", "content": (result.get("output_ref") or "")[:300]})
    print(f"\\n{'━'*65}")
    print(f"  Query  : {query}")
    print(f"  Intent : {result['intent']}   Output: {result['output_type']}")
    print(f"{'━'*65}")
    print((result.get("output_ref") or "")[:700])
    if len(result.get("output_ref") or "") > 700:
        print("…")
    return result


_ = run("Explain the overall architecture of this project")
_ = run("Show me the dependency diagram")
_ = run("How does login work under the hood?",          ["src/auth.ts"])
_ = run("Generate vitest unit tests for the Router",    ["src/routes.ts"])
'''))

# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 8 – Socket.io smoke test
# ═══════════════════════════════════════════════════════════════════════════════

cells.append(md("""
## 8  Socket.io Client Smoke Test

Tests the **running Entiendo server** by replaying the same Socket.io events
the browser sends.

**Start the server first:**
```bash
cd /path/to/Entiendo
npm install
npm run dev        # listens on http://localhost:3000
```
Then uncomment the last line in the cell and run.
"""))

cells.append(code('''
import socketio, time

SERVER_URL = "http://localhost:3000"

def smoke_test(
    repo_url: str = "vitejs/vite",
    query: str    = "Explain the architecture",
    timeout: int  = 90,
) -> List:
    sio      = socketio.Client(logger=False, engineio_logger=False)
    received = []

    @sio.event
    def connect():
        print(f"[CONNECTED]  {SERVER_URL}")

    @sio.on("clone_start")
    def on_clone_start(d):  print(f"[CLONE START] {d}")

    @sio.on("clone_done")
    def on_clone_done(d):   print(f"[CLONE DONE]  {d}")

    @sio.on("repo_structure")
    def on_structure(d):
        print(f"[STRUCTURE]  {len(d.get('tree', []))} files")
        received.append(("structure", len(d.get("tree", []))))

    @sio.on("log")
    def on_log(d):          print(f"[LOG]   {d.get('message','')}")

    @sio.on("token")
    def on_token(d):        print(d.get("token", ""), end="", flush=True)

    @sio.on("node_complete")
    def on_complete(d):
        print(f"\\n[NODE COMPLETE]  node={d.get('node')}")
        received.append(("complete", d.get("node")))

    @sio.on("error")
    def on_error(d):
        print(f"[ERROR]  {d}")
        received.append(("error", d))

    try:
        sio.connect(SERVER_URL, wait_timeout=5)
    except Exception as exc:
        print(f"Cannot connect — server running?\\n  {exc}")
        print("\\nRun:  npm run dev")
        return []

    sio.emit("agent_query", {"query": query, "repo_url": repo_url})
    deadline = time.time() + timeout
    while time.time() < deadline:
        if any(r[0] == "complete" for r in received):
            break
        time.sleep(1)
    sio.disconnect()
    print(f"\\nDone. Events: {received}")
    return received


# ─── Uncomment after starting: npm run dev ───────────────────────────────────
# results = smoke_test("vitejs/vite", "Explain the architecture")
print("Smoke test ready. Uncomment the last line after starting: npm run dev")
'''))

# ═══════════════════════════════════════════════════════════════════════════════
# Write notebook
# ═══════════════════════════════════════════════════════════════════════════════

notebook = {
    "nbformat": 4,
    "nbformat_minor": 5,
    "metadata": {
        "kernelspec": {
            "display_name": "Python 3",
            "language": "python",
            "name": "python3",
        },
        "language_info": {"name": "python", "version": "3.11.0"},
    },
    "cells": cells,
}

out = Path("/home/user/Entiendo/entiendo_pipeline_test.ipynb")
out.write_text(json.dumps(notebook, indent=1, ensure_ascii=False))
print(f"\nNotebook written → {out}  ({out.stat().st_size // 1024} KB)")
print(f"Total cells: {len(cells)}")
