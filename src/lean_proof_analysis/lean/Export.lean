import Lean
import Lean.Util.FoldConsts

/-!
Export elaborated declarations from an existing Lean environment as JSONL.
This inspects ConstantInfo and Expr; it does not check theorem correctness.
Run using the analyzed project's own Lean toolchain and built module path.
-/

open Lean

namespace LPAF.Export

structure ExportOptions where
  modules : Array String := #[]
  prefixes : Array String := #[]
  names : Array String := #[]
  maxDeclarations : Nat := 1000
  maxNodes : Nat := 100000

def usage : String :=
  "Usage: lean --run Export.lean --module MODULE [--module MODULE] " ++
  "[--prefix PREFIX] [--name FULL_NAME] [--max-declarations N] [--max-nodes N]\n" ++
  "Requires already-built modules and the target project's Lean toolchain. " ++
  "Outputs one JSON object per line. No proof-correctness verdict is produced."

def positiveNat (option value : String) : Except String Nat := do
  match value.toNat? with
  | some n => if n > 0 then pure n else throw s!"{option} must be positive"
  | none => throw s!"{option} must be a positive integer"

def parseArgs : List String → ExportOptions → Except String ExportOptions
  | [], options =>
    if options.modules.isEmpty then .error "At least one --module is required"
    else .ok options
  | "--module" :: value :: rest, options =>
    if value.isEmpty then .error "--module cannot be empty"
    else parseArgs rest { options with modules := options.modules.push value }
  | "--prefix" :: value :: rest, options =>
    if value.isEmpty then .error "--prefix cannot be empty"
    else parseArgs rest { options with prefixes := options.prefixes.push value }
  | "--name" :: value :: rest, options =>
    if value.isEmpty then .error "--name cannot be empty"
    else parseArgs rest { options with names := options.names.push value }
  | "--max-declarations" :: value :: rest, options => do
    let n ← positiveNat "--max-declarations" value
    parseArgs rest { options with maxDeclarations := n }
  | "--max-nodes" :: value :: rest, options => do
    let n ← positiveNat "--max-nodes" value
    parseArgs rest { options with maxNodes := n }
  | option :: _, _ => .error s!"Unknown or incomplete option: {option}"

def binderInfoName : BinderInfo → String
  | .default => "default"
  | .implicit => "implicit"
  | .strictImplicit => "strictImplicit"
  | .instImplicit => "instImplicit"

/-- Constructor data and child order are explicit; binder display names are separate. -/
def shape (e : Expr) : String × Array String × Array Expr × Option String :=
  match e with
  | .bvar index => ("bvar", #[toString index], #[], none)
  | .fvar id => ("fvar", #[id.name.toString], #[], none)
  | .mvar id => ("mvar", #[id.name.toString], #[], none)
  | .sort level => ("sort", #[toString level], #[], none)
  | .const name levels => ("const", #[name.toString] ++ levels.toArray.map toString, #[], none)
  | .app fn arg => ("app", #[], #[fn, arg], none)
  | .lam name type body info => ("lam", #[binderInfoName info], #[type, body], some name.toString)
  | .forallE name type body info => ("forallE", #[binderInfoName info], #[type, body], some name.toString)
  | .letE name type value body nonDep =>
    ("letE", #[toString nonDep], #[type, value, body], some name.toString)
  | .lit (.natVal value) => ("lit", #["nat", toString value], #[], none)
  | .lit (.strVal value) => ("lit", #["str", value], #[], none)
  | .mdata metadata body => ("mdata", #[reprStr metadata], #[body], none)
  | .proj typeName index body => ("proj", #[typeName.toString, toString index], #[body], none)

/--
Iterative postorder traversal avoids recursion proportional to expression depth.
Hash-consed completed nodes are shared. Child indices always precede their parent.
On the node limit, no partial graph is returned as if it were complete.
-/
def encodeExpr (expression : Expr) (maxNodes : Nat) : Except String Json := Id.run do
  let mut pending : List (Expr × Bool) := [(expression, false)]
  let mut seen : Std.HashMap Expr Nat := {}
  let mut nodes : Array Json := #[]
  while !pending.isEmpty do
    let (current, ready) := pending.head!
    pending := pending.tail!
    if seen.contains current then
      continue
    let (tag, data, children, binderName) := shape current
    if !ready then
      pending := (current, true) :: pending
      for child in children.reverse do
        if !seen.contains child then
          pending := (child, false) :: pending
    else
      if nodes.size >= maxNodes then
        return .error "node_limit"
      let mut childIds : Array Nat := #[]
      for child in children do
        match seen[child]? with
        | some index => childIds := childIds.push index
        | none => return .error "internal_missing_child"
      let fields := [("tag", toJson tag), ("data", toJson data), ("children", toJson childIds)]
      let fields := match binderName with
        | some name => fields ++ [("binder_name", toJson name)]
        | none => fields
      seen := seen.insert current nodes.size
      nodes := nodes.push (Json.mkObj fields)
  match seen[expression]? with
  | none => return .error "internal_missing_root"
  | some root => return .ok <| Json.mkObj [
      ("nodes", toJson nodes), ("root", toJson root), ("truncated", toJson false)]

def constantKind : ConstantInfo → String
  | .axiomInfo _ => "axiom"
  | .defnInfo _ => "definition"
  | .thmInfo _ => "theorem"
  | .opaqueInfo _ => "opaque"
  | .quotInfo _ => "quotient"
  | .inductInfo _ => "inductive"
  | .ctorInfo _ => "constructor"
  | .recInfo _ => "recursor"

def referenceNames (expression : Expr) : Array String :=
  expression.getUsedConstants.map Name.toString |>.qsort (· < ·)

def expressionRecord (expression : Option Expr) (maxNodes : Nat) : Json × String :=
  match expression with
  | none => (Json.null, "no_value")
  | some expression =>
    match encodeExpr expression maxNodes with
    | .ok value => (value, "available")
    | .error status => (Json.null, status)

def originModule (environment : Environment) (name : Name) : Option String := do
  let index ← environment.getModuleIdxFor? name
  let module ← environment.header.modules[index]?
  pure module.module.toString

def declarationRecord (environment : Environment) (constant : ConstantInfo)
    (options : ExportOptions) : Json := Id.run do
  let value := constant.value? (allowOpaque := true)
  let (typeExpr, typeStatus) := expressionRecord (some constant.type) options.maxNodes
  let (valueExpr, valueStatus) := expressionRecord value options.maxNodes
  return Json.mkObj [
    ("record", toJson "declaration"), ("id", toJson constant.name.toString),
    ("name", toJson constant.name.toString), ("kind", toJson (constantKind constant)),
    ("module", toJson (originModule environment constant.name)),
    ("evidence", toJson "lean_elaborated"), ("source_url", Json.null),
    ("level_params", toJson (constant.levelParams.map Name.toString)),
    ("type_expr", typeExpr), ("value_expr", valueExpr),
    ("expression_status", Json.mkObj [("type", toJson typeStatus), ("value", toJson valueStatus)]),
    ("references", Json.mkObj [
      ("type", toJson (referenceNames constant.type)),
      ("value", toJson (value.map referenceNames |>.getD #[]))]),
    ("references_complete", toJson true)]

def selected (options : ExportOptions) (name : Name) : Bool :=
  let text := name.toString
  (options.prefixes.isEmpty && options.names.isEmpty) || options.names.contains text ||
    options.prefixes.any (fun prefixName => text == prefixName || text.startsWith (prefixName ++ "."))

def runExport (options : ExportOptions) : IO Unit := do
  initSearchPath (← findSysroot)
  let imports := options.modules.map fun name => ({ module := name.toName } : Import)
  let environment ← importModules imports {} (loadExts := false)
  let constants := environment.constants.toList.toArray.filter (fun pair => selected options pair.1)
    |>.qsort (fun left right => left.1.toString < right.1.toString)
  let stdout ← IO.getStdout
  let header := Json.mkObj [
    ("record", toJson "header"), ("schema", toJson "lpaf-corpus-v0.1"),
    ("extractor", toJson "lpaf-lean-expr-v0.1"), ("lean_version", toJson Lean.versionString),
    ("modules", toJson options.modules), ("prefixes", toJson options.prefixes),
    ("names", toJson options.names), ("evidence", toJson "lean_elaborated"),
    ("not_proof_check", toJson true),
    ("normalization", toJson "No reduction; binder names separate; universes, literals and metadata retained"),
    ("source_locations", toJson "unavailable")]
  stdout.putStrLn header.compress
  for (_, constant) in constants[:options.maxDeclarations] do
    stdout.putStrLn (declarationRecord environment constant options).compress
  let footer := Json.mkObj [
    ("record", toJson "footer"), ("declarations", toJson (min constants.size options.maxDeclarations)),
    ("matched_declarations", toJson constants.size),
    ("complete", toJson (decide (constants.size <= options.maxDeclarations))),
    ("limits", Json.mkObj [("max_declarations", toJson options.maxDeclarations),
                          ("max_nodes_per_expression", toJson options.maxNodes)])]
  stdout.putStrLn footer.compress

end LPAF.Export

def main (args : List String) : IO UInt32 := do
  if args.contains "--help" then
    IO.println LPAF.Export.usage
    return 0
  match LPAF.Export.parseArgs args {} with
  | .error message =>
    (← IO.getStderr).putStrLn message
    return 2
  | .ok options =>
    try
      LPAF.Export.runExport options
      return 0
    catch error =>
      (← IO.getStderr).putStrLn s!"Lean extraction failed: {error}"
      return 1
