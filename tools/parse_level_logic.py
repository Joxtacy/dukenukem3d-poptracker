"""AST-parse each Duke3D apworld level and emit per-location PopTracker
access rules that mirror the apworld's region graph.

Pipeline per level:
  1. parse_level_graph(path) — walks the class' main_region() method, builds
     {regions, edges, per-location restricts, events}.
  2. translate_rule(node, ctx) — converts a Python rule expression (r.X,
     r.has(...), self.red_key, &/| operators) into a symbolic Rule tree.
  3. compute_location_rules(graph, prefix) — for each location, computes the
     reachability rule from the main_region to that location's region, ANDs
     in any restrict rule, and returns DNF (list of conjunctions).
  4. emit_access_rules(dnf) — formats the DNF as PopTracker access_rules.

Top-level entry: compute_all_level_rules(apworld_dir).
"""
from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

# ---------------------------------------------------------------------------
# Symbolic rule tree
# ---------------------------------------------------------------------------


class Rule:
    """Marker base class."""


@dataclass(frozen=True)
class Lit(Rule):
    """A literal: a tracker code (e.g. 'jump') or a $-prefixed Lua function
    reference (e.g. '$can_jump', '$has_group_explosives').

    For codes with count modifiers, encode as 'code:N'.
    """
    name: str

    def __str__(self) -> str:  # for debugging
        return self.name


@dataclass(frozen=True)
class And(Rule):
    children: tuple[Rule, ...]


@dataclass(frozen=True)
class Or(Rule):
    children: tuple[Rule, ...]


class _True(Rule):
    def __repr__(self) -> str:
        return "TRUE"


class _False(Rule):
    def __repr__(self) -> str:
        return "FALSE"


TRUE = _True()
FALSE = _False()


def AND(*rules: Rule) -> Rule:
    """Smart constructor: drops TRUE, short-circuits on FALSE, flattens."""
    out: list[Rule] = []
    for r in rules:
        if r is TRUE:
            continue
        if r is FALSE:
            return FALSE
        if isinstance(r, And):
            out.extend(r.children)
        else:
            out.append(r)
    if not out:
        return TRUE
    if len(out) == 1:
        return out[0]
    return And(tuple(out))


def OR(*rules: Rule) -> Rule:
    """Smart constructor: drops FALSE, short-circuits on TRUE, flattens."""
    out: list[Rule] = []
    for r in rules:
        if r is FALSE:
            continue
        if r is TRUE:
            return TRUE
        if isinstance(r, Or):
            out.extend(r.children)
        else:
            out.append(r)
    if not out:
        return FALSE
    if len(out) == 1:
        return out[0]
    return Or(tuple(out))


# ---------------------------------------------------------------------------
# DNF + emission
# ---------------------------------------------------------------------------


def to_dnf(rule: Rule) -> list[list[Lit]]:
    """Return rule as a list of conjunctions (each conjunction is a list of
    literals). [] means FALSE; [[]] means TRUE."""
    if rule is TRUE:
        return [[]]
    if rule is FALSE:
        return []
    if isinstance(rule, Lit):
        return [[rule]]
    if isinstance(rule, And):
        result: list[list[Lit]] = [[]]
        for child in rule.children:
            child_dnf = to_dnf(child)
            if not child_dnf:  # child is FALSE
                return []
            new_result: list[list[Lit]] = []
            for r in result:
                for c in child_dnf:
                    new_result.append(r + c)
            result = new_result
        return _dedupe_dnf(result)
    if isinstance(rule, Or):
        result = []
        for child in rule.children:
            result.extend(to_dnf(child))
        return _dedupe_dnf(result)
    raise TypeError(f"unknown rule type: {type(rule)}")


def _dedupe_dnf(dnf: list[list[Lit]]) -> list[list[Lit]]:
    """Remove duplicate conjunctions and within-conjunction duplicate literals.
    Drops conjunctions that are supersets of others (less restrictive →
    redundant); the smaller one already covers them."""
    cleaned: list[frozenset[str]] = []
    for conj in dnf:
        s = frozenset(lit.name for lit in conj)
        if not any(other <= s and other != s for other in cleaned):
            cleaned = [c for c in cleaned if not s <= c or c == s]
            if s not in cleaned:
                cleaned.append(s)
    # Convert back to lit lists, preserving stable order
    out = []
    for s in cleaned:
        out.append(sorted([Lit(name) for name in s], key=lambda l: l.name))
    return out


def emit_access_rules(rule: Rule) -> list[str]:
    """Format the rule as a PopTracker access_rules array. Empty array means
    unreachable; a single empty string means always reachable (caller should
    omit the field)."""
    dnf = to_dnf(rule)
    return [",".join(lit.name for lit in conj) for conj in dnf]


# ---------------------------------------------------------------------------
# Translation context
# ---------------------------------------------------------------------------


# Items in groups (mirrors items/__init__.py's item_groups). Each entry is
# the tracker codes that satisfy "has any of group X".
_GROUP_CODES: dict[str, list[str]] = {
    "Explosives": ["rpg", "progressive_rpg", "pipebomb", "progressive_pipebomb",
                   "devastator", "progressive_devastator", "tripmine",
                   "progressive_tripmine"],
    "RPG": ["rpg", "progressive_rpg"],
    "Pipebomb": ["pipebomb", "progressive_pipebomb"],
    "Devastator": ["devastator", "progressive_devastator"],
    "Tripmine": ["tripmine", "progressive_tripmine"],
    "Jetpack": ["jetpack", "progressive_jetpack"],
    "Jetpack Capacity": ["jetpack", "jetpack_capacity", "progressive_jetpack"],
    "Steroids": ["steroids", "progressive_steroids"],
    "Steroids Capacity": ["steroids", "steroids_capacity", "progressive_steroids"],
    "Scuba Gear": ["scuba_gear", "progressive_scuba_gear"],
    "Scuba Gear Capacity": ["scuba_gear", "scuba_gear_capacity",
                            "progressive_scuba_gear"],
}


def _group_or(group: str) -> Rule:
    codes = _GROUP_CODES.get(group)
    if codes is None:
        # Unknown group; degrade to permissive (TRUE) so we don't accidentally
        # block a location from being checkable.
        return TRUE
    return OR(*[Lit(c) for c in codes])


@dataclass
class Ctx:
    """Translation context for a single level."""
    prefix: str           # e.g. "E1L1"
    cp: str               # lowercase prefix, e.g. "e1l1"
    events: set[str]      # event names defined on this level
    # Per-event resolved access rule (filled lazily by resolve_event_rules).
    event_rules: dict[str, Rule] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Translate an apworld rule expression AST node into a symbolic Rule.
# ---------------------------------------------------------------------------


_DIFF_LIT = {
    "easy": Lit("$logic_easy"),
    "medium": Lit("$logic_medium"),
    "hard": Lit("$logic_hard"),
    "extreme": Lit("$logic_extreme"),
}


def translate_rule(node: ast.AST, ctx: Ctx) -> Rule:  # noqa: C901
    """Walk a Python expression AST and produce a symbolic Rule. Anything
    we can't recognize becomes TRUE (permissive) so we never block a
    location. Warnings logged to stderr if needed."""

    # Boolean ops via & | (BitOp in AST)
    if isinstance(node, ast.BinOp):
        if isinstance(node.op, ast.BitAnd):
            return AND(translate_rule(node.left, ctx),
                       translate_rule(node.right, ctx))
        if isinstance(node.op, ast.BitOr):
            return OR(translate_rule(node.left, ctx),
                      translate_rule(node.right, ctx))

    # Parenthesized expressions / unary, etc. — fall through to ast.unparse path
    # if we hit something unexpected we'll log and return TRUE.

    # r.X / self.Y attribute access, possibly with a Call (e.g. r.jetpack(50))
    if isinstance(node, ast.Attribute):
        return _translate_attr(node, ctx, args=None)

    if isinstance(node, ast.Call):
        # r.has("Name") / r.has_group("Name") / r.count(...) / r.jetpack(50) /
        # r.dive(50) / r.difficulty("medium") / self.event("...")
        if isinstance(node.func, ast.Attribute):
            return _translate_attr(node.func, ctx, args=node.args)
        # bare function call (rare)
        return TRUE

    if isinstance(node, ast.Constant):
        # Literal True/False (rare; e.g. r.true is an Attribute, not a Constant)
        if node.value is True:
            return TRUE
        if node.value is False:
            return FALSE

    # Anything else: permissive default
    return TRUE


def _translate_attr(node: ast.Attribute, ctx: Ctx,
                    args: list[ast.AST] | None) -> Rule:  # noqa: C901
    """Translate r.X or self.X attribute (possibly called with args)."""
    base = node.value
    attr = node.attr

    # self.* attributes
    if isinstance(base, ast.Name) and base.id == "self":
        if attr in ("red_key", "blue_key", "yellow_key"):
            color = attr.split("_")[0]
            # red_key = can_use & has(prefix Color Key Card)
            return AND(Lit("$can_use"), Lit(f"{ctx.cp}_{color}_key"))
        if attr == "event":
            # self.event("name") → resolve to the event's own access rule.
            if not args or not isinstance(args[0], ast.Constant):
                return TRUE
            event_name = args[0].value
            return ctx.event_rules.get(event_name, TRUE)

    # r.X attributes
    if isinstance(base, ast.Name) and base.id == "r":
        # No-arg primitives
        if args is None:
            return _r_attr_no_args(attr, ctx)
        # Called primitives: r.has(name), r.has_group, r.count, r.jetpack(N), etc.
        return _r_attr_with_args(attr, args, ctx)

    return TRUE


def _r_attr_no_args(attr: str, ctx: Ctx) -> Rule:  # noqa: C901
    if attr == "true":
        return TRUE
    if attr == "false":
        return FALSE
    if attr == "can_jump":
        return Lit("$can_jump")
    if attr == "can_crouch":
        return Lit("$can_crouch")
    if attr == "can_sprint":
        return Lit("$can_sprint")
    if attr == "can_dive":
        return Lit("$can_dive")
    if attr == "can_open":
        return Lit("$can_open")
    if attr == "can_use":
        return Lit("$can_use")
    if attr == "can_shrink":
        return TRUE  # always available per rules.py
    if attr == "jump":
        return Lit("$jump")  # can_jump | jetpack(50)
    if attr == "sprint":
        return Lit("$sprint")  # can_sprint | steroids
    if attr == "fast_sprint":
        return Lit("$fast_sprint")  # can_sprint & steroids
    if attr == "sr50":
        return Lit("$sr50")  # sprint | logic_hard
    if attr == "steroids":
        return _group_or("Steroids")
    if attr == "rpg":
        return _group_or("RPG")
    if attr == "pipebomb":
        return _group_or("Pipebomb")
    if attr == "devastator":
        return _group_or("Devastator")
    if attr == "tripmine":
        return _group_or("Tripmine")
    if attr == "explosives":
        return _group_or("Explosives")
    if attr == "glitched":
        return Lit("$glitched")
    if attr == "crouch_jump":
        return Lit("$crouch_jump")
    if attr == "fast_crouch_jump":
        return Lit("$fast_crouch_jump")
    if attr == "glitch_kick":
        return Lit("$glitch_kick")
    if attr in ("can_kill_boss_1", "can_kill_boss_2",
                "can_kill_boss_3", "can_kill_boss_4"):
        return Lit(f"${attr}")
    return TRUE  # unknown: permissive


def _r_attr_with_args(attr: str, args: list[ast.AST], ctx: Ctx) -> Rule:
    if attr == "has" and args and isinstance(args[0], ast.Constant):
        return Lit(_item_name_to_code(args[0].value, ctx))
    if attr == "has_group" and args and isinstance(args[0], ast.Constant):
        return _group_or(args[0].value)
    if attr == "count" and len(args) >= 2 and \
            isinstance(args[0], ast.Constant) and isinstance(args[1], ast.Constant):
        # Items received: code with :N modifier
        code = _item_name_to_code(args[0].value, ctx)
        return Lit(f"{code}:{args[1].value}")
    if attr == "count_group" and len(args) >= 2 and \
            isinstance(args[0], ast.Constant) and isinstance(args[1], ast.Constant):
        # Approximate: at least one in group; lose count granularity.
        return _group_or(args[0].value)
    if attr == "jetpack":
        # r.jetpack(N) → simplification: has-any-jetpack. Fuel granularity is v0.4.
        return _group_or("Jetpack")
    if attr == "dive":
        # r.dive(N) → can_dive & has-scuba. Simplification on fuel.
        return AND(Lit("$can_dive"), _group_or("Scuba Gear"))
    if attr == "difficulty" and args and isinstance(args[0], ast.Constant):
        lit = _DIFF_LIT.get(args[0].value)
        return lit if lit is not None else TRUE
    if attr == "explosives_count":
        # Simplify to "has any explosive"; count granularity is v0.4.
        return _group_or("Explosives")
    return TRUE


def _item_name_to_code(name: str, ctx: Ctx) -> str:
    """Translate an apworld item name like 'E1L1 Red Key Card' or 'Jump' to
    the tracker code."""
    # Per-level items follow the prefix pattern.
    if name.startswith(f"{ctx.prefix} "):
        rest = name[len(ctx.prefix) + 1:]
        if rest.endswith(" Key Card"):
            color = rest[:-len(" Key Card")].lower()
            return f"{ctx.cp}_{color}_key"
        if rest == "Automap":
            return f"{ctx.cp}_automap"
        if rest == "Unlock":
            return f"{ctx.cp}_unlock"
        # Event names fall here as e.g. "E1L3 Unlock Cell Blocks"; we shouldn't
        # be calling into _item_name_to_code for events directly.
    # Global items: lowercase + replace spaces with underscores.
    return name.lower().replace(" ", "_")


# ---------------------------------------------------------------------------
# Region graph extraction
# ---------------------------------------------------------------------------


@dataclass
class LevelGraph:
    prefix: str
    main_region: str
    region_locations: dict[str, list[str]]   # region name -> location list
    edges: list[tuple[str, str, ast.AST | None]]  # (src, dst, raw rule AST)
    restrict_asts: dict[str, ast.AST]   # location_name -> raw rule AST
    events: set[str]


def parse_level_graph(level_path: Path) -> LevelGraph:
    src = level_path.read_text()
    tree = ast.parse(src)
    cls = next(n for n in ast.walk(tree) if isinstance(n, ast.ClassDef))

    levelnum = volumenum = 0
    name = ""
    events: set[str] = set()
    for stmt in cls.body:
        if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1 and \
                isinstance(stmt.targets[0], ast.Name):
            tname = stmt.targets[0].id
            try:
                val = ast.literal_eval(stmt.value)
            except Exception:
                continue
            if tname == "levelnum":
                levelnum = val
            elif tname == "volumenum":
                volumenum = val
            elif tname == "name":
                name = val
            elif tname == "events":
                events = set(val)

    prefix = f"E{volumenum + 1}L{levelnum + 1}"
    self_attrs = {"name": name, "prefix": prefix}

    # Collect all location names defined on the class (for list-comprehension
    # shortcuts like `[loc["name"] for loc in self.location_defs]`).
    all_loc_names: list[str] = []
    for stmt in cls.body:
        if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1 and \
                isinstance(stmt.targets[0], ast.Name) and \
                stmt.targets[0].id == "location_defs":
            try:
                defs = ast.literal_eval(stmt.value)
                all_loc_names = [d["name"] for d in defs]
            except Exception:
                pass

    main_region_method = next(
        (s for s in cls.body if isinstance(s, ast.FunctionDef) and s.name == "main_region"),
        None,
    )
    if main_region_method is None:
        return LevelGraph(prefix=prefix, main_region="", region_locations={},
                          edges=[], restrict_asts={}, events=events)

    region_locations: dict[str, list[str]] = {}
    edges: list[tuple[str, str, ast.AST | None]] = []
    restrict_asts: dict[str, ast.AST] = {}
    var_to_region: dict[str, str] = {}
    main_region_name: str | None = None

    for stmt in main_region_method.body:
        # var = self.region(...) (or self.region(..., [...])  )
        if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1 and \
                isinstance(stmt.targets[0], ast.Name) and \
                isinstance(stmt.value, ast.Call):
            call = stmt.value
            if _is_self_call(call, "region"):
                rname = _eval_string_arg(call.args[0], prefix, self_attrs)
                if rname is None:
                    continue
                full_name = f"{prefix} {rname}"
                region_locations[full_name] = []
                if len(call.args) >= 2:
                    locs = _eval_string_list(call.args[1], prefix, self_attrs,
                                             all_loc_names)
                    region_locations[full_name] = locs
                var_to_region[stmt.targets[0].id] = full_name
                if main_region_name is None:
                    main_region_name = full_name

        elif isinstance(stmt, ast.Expr) and (
                isinstance(stmt.value, ast.Call) or (
                    isinstance(stmt.value, ast.Tuple)
                    and len(stmt.value.elts) == 1
                    and isinstance(stmt.value.elts[0], ast.Call)
                )):
            # Handle the rare case where a trailing comma in the source
            # turns a self.connect(...) into a 1-tuple — same effect for us.
            call = stmt.value if isinstance(stmt.value, ast.Call) \
                else stmt.value.elts[0]
            if _is_self_call(call, "connect") and len(call.args) >= 2:
                src_var = call.args[0]
                dst_var = call.args[1]
                if not (isinstance(src_var, ast.Name) and isinstance(dst_var, ast.Name)):
                    continue
                src_name = var_to_region.get(src_var.id)
                dst_name = var_to_region.get(dst_var.id)
                if not src_name or not dst_name:
                    continue
                rule_node = call.args[2] if len(call.args) >= 3 else None
                edges.append((src_name, dst_name, rule_node))
            elif _is_self_call(call, "restrict") and len(call.args) >= 2:
                loc_name = _eval_string_arg(call.args[0], prefix, self_attrs)
                if loc_name is None:
                    continue
                full_loc = f"{prefix} {loc_name}"
                restrict_asts[full_loc] = call.args[1]
            elif _is_self_call(call, "add_locations") and len(call.args) >= 2:
                # self.add_locations([loc, loc, ...], region_var)
                locs = _eval_string_list(call.args[0], prefix, self_attrs,
                                         all_loc_names)
                region_arg = call.args[1]
                if isinstance(region_arg, ast.Name) and \
                        region_arg.id in var_to_region:
                    target_region = var_to_region[region_arg.id]
                    region_locations.setdefault(target_region, []).extend(locs)
            elif _is_self_call(call, "add_location") and len(call.args) >= 2:
                # self.add_location(loc, region_var)
                loc = _eval_string_arg(call.args[0], prefix, self_attrs)
                region_arg = call.args[1]
                if loc and isinstance(region_arg, ast.Name) and \
                        region_arg.id in var_to_region:
                    target_region = var_to_region[region_arg.id]
                    region_locations.setdefault(target_region, []).append(loc)

    return LevelGraph(
        prefix=prefix,
        main_region=main_region_name or "",
        region_locations=region_locations,
        edges=edges,
        restrict_asts=restrict_asts,
        events=events,
    )


def _is_self_call(call: ast.Call, attr: str) -> bool:
    return (isinstance(call.func, ast.Attribute) and
            isinstance(call.func.value, ast.Name) and
            call.func.value.id == "self" and
            call.func.attr == attr)


def _eval_string_arg(node: ast.AST, prefix: str,
                     self_attrs: dict[str, str] | None = None) -> str | None:
    self_attrs = self_attrs or {}
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    # self.name / self.prefix etc.
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and \
            node.value.id == "self" and node.attr in self_attrs:
        return self_attrs[node.attr]
    # f"..." with simple substitutions (handle self.X interpolations)
    if isinstance(node, ast.JoinedStr):
        out = []
        for part in node.values:
            if isinstance(part, ast.Constant):
                out.append(part.value)
            elif isinstance(part, ast.FormattedValue) and \
                    isinstance(part.value, ast.Attribute) and \
                    isinstance(part.value.value, ast.Name) and \
                    part.value.value.id == "self" and \
                    part.value.attr in self_attrs:
                out.append(self_attrs[part.value.attr])
            else:
                return None
        return "".join(out)
    return None


def _eval_string_list(node: ast.AST, prefix: str,
                      self_attrs: dict[str, str] | None = None,
                      all_loc_names: list[str] | None = None) -> list[str]:
    if isinstance(node, (ast.List, ast.Tuple)):
        return [s for s in (_eval_string_arg(e, prefix, self_attrs) for e in node.elts)
                if s is not None]
    # Recognise [loc["name"] for loc in self.location_defs] and similar.
    if isinstance(node, ast.ListComp) and all_loc_names is not None:
        return list(all_loc_names)
    return []


# ---------------------------------------------------------------------------
# Event resolution + reachability
# ---------------------------------------------------------------------------


def _location_in_region(loc_name: str, graph: LevelGraph) -> str | None:
    """Find which region contains the named location (full prefix-included)."""
    for region, locs in graph.region_locations.items():
        for loc in locs:
            if f"{graph.prefix} {loc}" == loc_name:
                return region
    return None


def resolve_event_rules(graph: LevelGraph, ctx: Ctx) -> dict[str, Rule]:
    """For each event, compute the access rule for its triggering location.

    The event location is referenced by self.event("name") and lives in the
    region graph just like a normal location. The event "fires" when that
    location is collectible — i.e., when the region containing it is
    reachable AND any per-location restrict is satisfied.

    First pass: assume events resolve to TRUE; then iterate to convergence.
    """
    # Initialise to TRUE so cyclic event dependencies don't crash.
    ctx.event_rules = {ev: TRUE for ev in graph.events}

    for _ in range(4):  # fixed-point with cap; events almost never chain deeply
        changed = False
        for event_name in graph.events:
            full_loc = f"{graph.prefix} {event_name}"
            region = _location_in_region(full_loc, graph)
            if region is None:
                continue
            region_rule = compute_region_rule(graph, ctx, region)
            restrict_ast = graph.restrict_asts.get(full_loc)
            restrict_rule = (translate_rule(restrict_ast, ctx)
                             if restrict_ast is not None else TRUE)
            new_rule = AND(region_rule, restrict_rule)
            if new_rule != ctx.event_rules.get(event_name):
                ctx.event_rules[event_name] = new_rule
                changed = True
        if not changed:
            break
    return ctx.event_rules


def compute_region_rule(graph: LevelGraph, ctx: Ctx, target: str) -> Rule:
    """Compute the access rule for a region by exploring all paths from
    main_region to target. Conservative: bounded by visited-set + path-rule
    accumulator to avoid infinite loops in cyclic graphs."""
    if target == graph.main_region:
        return TRUE

    # Adjacency list: dst -> [(src, rule_ast)]
    incoming: dict[str, list[tuple[str, ast.AST | None]]] = {}
    for src, dst, rule in graph.edges:
        incoming.setdefault(dst, []).append((src, rule))

    # Memoize results per region.
    memo: dict[str, Rule] = {graph.main_region: TRUE}

    def visit(node: str, on_stack: frozenset[str]) -> Rule:
        if node in memo:
            return memo[node]
        if node in on_stack:
            return FALSE  # break cycles; this path contributes nothing
        on_stack2 = on_stack | {node}
        alts = []
        for src, rule_ast in incoming.get(node, []):
            src_rule = visit(src, on_stack2)
            if src_rule is FALSE:
                continue
            edge_rule = translate_rule(rule_ast, ctx) if rule_ast is not None else TRUE
            alts.append(AND(src_rule, edge_rule))
        result = OR(*alts) if alts else FALSE
        memo[node] = result
        return result

    return visit(target, frozenset())


def compute_location_rule(graph: LevelGraph, ctx: Ctx, loc_name: str) -> Rule:
    """Full access rule for a single location (prefix-included)."""
    region = _location_in_region(loc_name, graph)
    if region is None:
        return TRUE  # location not in any region — shouldn't happen
    region_rule = compute_region_rule(graph, ctx, region)
    restrict_ast = graph.restrict_asts.get(loc_name)
    restrict_rule = translate_rule(restrict_ast, ctx) if restrict_ast is not None else TRUE
    return AND(region_rule, restrict_rule)


# ---------------------------------------------------------------------------
# Top-level driver
# ---------------------------------------------------------------------------


def compute_all_level_rules(apworld_dir: Path) -> dict[str, dict[str, list[str]]]:
    """For every level file, compute access_rules for every location.

    Returns {prefix: {location_name_without_prefix: [rule_string, ...]}}.
    """
    out: dict[str, dict[str, list[str]]] = {}
    levels_dir = apworld_dir / "levels"
    for path in sorted(levels_dir.glob("e?l*.py")):
        if path.name == "__init__.py":
            continue
        graph = parse_level_graph(path)
        ctx = Ctx(prefix=graph.prefix, cp=graph.prefix.lower(),
                  events=graph.events)
        resolve_event_rules(graph, ctx)

        per_loc: dict[str, list[str]] = {}
        for region, locs in graph.region_locations.items():
            for loc in locs:
                if loc in graph.events:
                    continue  # internal events; not real AP locations
                full_name = f"{graph.prefix} {loc}"
                rule = compute_location_rule(graph, ctx, full_name)
                per_loc[loc] = emit_access_rules(rule)
        out[graph.prefix] = per_loc
    return out


if __name__ == "__main__":
    import sys
    apworld = Path(sys.argv[1]) if len(sys.argv) > 1 else \
        Path("/tmp/duke3d-apworld/extracted/duke3d")
    rules = compute_all_level_rules(apworld)
    print(f"Parsed {len(rules)} levels")
    sample = next(iter(rules))
    print(f"\nSample for {sample}:")
    for loc, rs in list(rules[sample].items())[:8]:
        print(f"  {loc}: {rs}")
