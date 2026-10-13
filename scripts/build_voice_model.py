"""Compile the logger's spoken DSL into the Vosk model's decoding graph.

The stock Vosk JSON grammar is a smoothed bigram language model. That limits
its vocabulary, but does not enforce command structure: after hearing "T" it
can still choose "A" because assists make A a globally valid word. This script
replaces Gr.fst with a deterministic graph of complete legal commands. Every
terminal state loops to the command root so back-to-back events remain valid.

Development dependencies (not needed by the web app):

    python3 -m pip install vosk kaldifst
    python3 scripts/build_voice_model.py
"""

from __future__ import annotations

import gzip
import hashlib
import json
import math
from pathlib import Path
import runpy
import shutil
import subprocess
import sys
import tarfile
import tempfile

import kaldifst


ROOT = Path(__file__).resolve().parent.parent
MODEL_ARCHIVE = ROOT / "docs/logger/models/vosk-model-small-en-us-0.15.tar.gz"
STOCK_GRAPH = ROOT / "scripts/voice-model/Gr.stock.fst.gz"
PLAYER_NUMBERS = [str(number) for number in range(100)]
ROSTER_NUMBERS = sorted(
    runpy.run_path(ROOT / "scripts/stats.py")["players"], key=int
)
# Two-point field-goal events outnumber free throws by about 4.8:1 in the game
# logs. Use that real domain prior only to break close G/T acoustic decisions;
# a clearly heard T still wins on acoustic evidence.
FREE_THROW_PRIOR_COST = math.log(4.8)


def spoken_grammar() -> tuple[list[str], dict[str, str]]:
    script = (
        "const d=require('./docs/logger/voice.js');"
        f"const players={json.dumps(PLAYER_NUMBERS)};"
        f"const lineup={json.dumps(ROSTER_NUMBERS)};"
        "process.stdout.write(JSON.stringify({"
        "commands:d.grammarCommands({players}),"
        "lineupPlayers:Object.fromEntries(lineup.map(n=>[n,d.spokenNumber(n)]))"
        "}));"
    )
    result = subprocess.run(
        ["node", "-e", script],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    grammar = json.loads(result.stdout)
    commands = grammar["commands"]
    if not commands or any(not command.strip() for command in commands):
        raise RuntimeError("voice.js returned an empty grammar command")
    return commands, grammar["lineupPlayers"]


def add_word_symbols(symbols: kaldifst.SymbolTable, words: dict[str, int]) -> None:
    symbols.add_symbol("<eps>", 0)
    for word, word_id in sorted(words.items(), key=lambda item: item[1]):
        symbols.add_symbol(word, word_id)


def model_word_ids(model_dir: Path, vocabulary: list[str]) -> dict[str, int]:
    # vosk and kaldifst each bundle OpenFST. Loading both native libraries into
    # one Python process can crash on macOS, so query Vosk in isolation.
    script = """
import json
import sys
import vosk

vosk.SetLogLevel(-1)
model = vosk.Model(sys.argv[1])
words = json.load(sys.stdin)
print(json.dumps({word: model.vosk_model_find_word(word) for word in words}))
"""
    result = subprocess.run(
        [sys.executable, "-c", script, str(model_dir)],
        input=json.dumps(vocabulary),
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def validate_model(model_dir: Path) -> None:
    script = """
import sys
import vosk

vosk.SetLogLevel(-1)
model = vosk.Model(sys.argv[1])
recognizer = vosk.KaldiRecognizer(model, 16000)
"""
    subprocess.run([sys.executable, "-c", script, str(model_dir)], check=True)


def compile_graph(
    model_dir: Path, commands: list[str], lineup_players: dict[str, str]
) -> kaldifst.StdVectorFst:
    phrases = ["[unk]", *commands]
    lineup_prefixes = ["i g", "i gee", "eye g", "eye gee"]
    vocabulary = sorted({
        word
        for phrase in [*phrases, *lineup_prefixes, *lineup_players.values()]
        for word in phrase.split()
    })
    word_ids = model_word_ids(model_dir, vocabulary)
    missing = [word for word, word_id in word_ids.items() if word_id < 0]
    if missing:
        raise RuntimeError("words missing from Vosk model: " + ", ".join(missing))

    graph = kaldifst.StdVectorFst()
    root = graph.add_state()
    graph.start = root
    graph.set_final(root, 0.0)

    edges: dict[tuple[int, int], int] = {}
    terminals: dict[int, float] = {}

    def next_state(state: int, word: str) -> int:
        label = word_ids[word]
        edge = (state, label)
        target = edges.get(edge)
        if target is None:
            target = graph.add_state()
            graph.add_arc(state, kaldifst.StdArc(label, label, 0.0, target))
            edges[edge] = target
        return target

    def add_words(state: int, words: list[str]) -> int:
        for word in words:
            state = next_state(state, word)
        return state

    def connect_words(state: int, words: list[str], target: int) -> None:
        for word in words[:-1]:
            state = next_state(state, word)
        label = word_ids[words[-1]]
        edge = (state, label)
        existing = edges.get(edge)
        if existing is not None and existing != target:
            raise RuntimeError("lineup grammar has an ambiguous player number")
        if existing is None:
            graph.add_arc(state, kaldifst.StdArc(label, label, 0.0, target))
            edges[edge] = target

    def command_cost(phrase: str) -> float:
        words = phrase.split()
        if (
            len(words) >= 3
            and words[0] in {"f", "eff"}
            and words[1] in {"t", "tee", "throw"}
        ):
            return FREE_THROW_PRIOR_COST
        return 0.0

    for phrase in phrases:
        terminal = add_words(root, phrase.split())
        cost = command_cost(phrase)
        terminals[terminal] = min(terminals.get(terminal, math.inf), cost)

    if len(lineup_players) < 5:
        raise RuntimeError("voice lineup grammar needs at least five roster players")
    lineup_root = graph.add_state()
    for prefix in lineup_prefixes:
        prefix_state = add_words(root, prefix.split())
        graph.add_arc(prefix_state, kaldifst.StdArc(0, 0, 0.0, lineup_root))

    # A state is the set of players already heard. This accepts every ordering
    # of five distinct roster players without expanding all permutations into
    # separate phrase strings.
    lineup_states: dict[frozenset[str], int] = {frozenset(): lineup_root}
    for size in range(5):
        for selected, state in list(lineup_states.items()):
            if len(selected) != size:
                continue
            for player, spoken in lineup_players.items():
                if player in selected:
                    continue
                next_selected = selected | {player}
                target = lineup_states.get(next_selected)
                if target is None:
                    target = graph.add_state()
                    lineup_states[next_selected] = target
                connect_words(state, spoken.split(), target)
    for selected, state in lineup_states.items():
        if len(selected) == 5:
            terminals[state] = 0.0

    # Epsilon returns join complete commands into a continuous language.
    # Determinization resolves those returns into an exact, epsilon-free loop.
    for state, cost in terminals.items():
        graph.add_arc(state, kaldifst.StdArc(0, 0, cost, root))

    symbols = kaldifst.SymbolTable("words")
    add_word_symbols(symbols, word_ids)
    graph.input_symbols = symbols
    graph.output_symbols = symbols

    stopped_early = kaldifst.determinize_star(graph)
    if stopped_early:
        raise RuntimeError("grammar determinization stopped before completion")
    kaldifst.minimize(graph)
    kaldifst.arcsort(graph, "ilabel")
    return graph


def accepts(graph: kaldifst.StdVectorFst, phrase: str) -> bool:
    symbols = graph.input_symbols
    state = graph.start
    for word in phrase.split():
        label = symbols.find(word)
        matches = [arc for arc in kaldifst.ArcIterator(graph, state) if arc.ilabel == label]
        if len(matches) != 1:
            return False
        state = matches[0].nextstate
    return math.isfinite(graph.final(state).value)


def path_cost(graph: kaldifst.StdVectorFst, phrase: str) -> float:
    symbols = graph.input_symbols
    state = graph.start
    cost = 0.0
    for word in phrase.split():
        label = symbols.find(word)
        matches = [arc for arc in kaldifst.ArcIterator(graph, state) if arc.ilabel == label]
        if len(matches) != 1:
            return math.inf
        cost += matches[0].weight.value
        state = matches[0].nextstate
    return cost + graph.final(state).value


def validate_graph_language(graph: kaldifst.StdVectorFst, commands: list[str]) -> None:
    rejected = [command for command in commands if not accepts(graph, command)]
    if rejected:
        raise RuntimeError("compiled graph rejects: " + ", ".join(rejected[:5]))

    sequences = [
        "f g a fourteen b three r three f g m three ay twenty one",
        "eff gee ay twenty two eff gee em five",
        "eff tee ay twenty two eff tee em twenty two",
        "three eff gee ay fourteen three eff gee em five",
        "tee oh twenty five ess twenty two",
        "t o twenty two f g a fourteen",
        "j ball gee f g m five",
        "j o jay fourteen dee jay five",
        "see fourteen thirty f g a fourteen",
        "see twenty zero ball gee eye gee one two three five fourteen",
        "eye gee one two three five fourteen f g a fourteen",
    ]
    for sequence in sequences:
        if not accepts(graph, sequence):
            raise RuntimeError("compiled graph rejects legal sequence: " + sequence)

    illegal = [
        "t a twenty five",
        "tee ay twenty five",
        "f g ess five",
        "ay oh",
        "ess galaxy",
        "tee",
        "t g",
        "tee gee",
        "t o",
        "tee oh",
        "f g a",
        "see twenty one",
        "see twenty zero one",
        "eye gee one one two three four",
        "eye gee one two three four",
        "eye gee one two three four five fourteen",
    ]
    for phrase in illegal:
        if accepts(graph, phrase):
            raise RuntimeError("compiled graph accepts illegal phrase: " + phrase)

    field_goal_cost = path_cost(graph, "f g a twenty two")
    free_throw_cost = path_cost(graph, "f t a twenty two")
    if not math.isclose(
        free_throw_cost - field_goal_cost, FREE_THROW_PRIOR_COST, abs_tol=1e-4
    ):
        raise RuntimeError(
            "compiled graph lost the field-goal/free-throw prior: "
            f"field goal={field_goal_cost}, free throw={free_throw_cost}"
        )

    symbols = graph.input_symbols
    for initial in ("t", "tee"):
        state = graph.start
        label = symbols.find(initial)
        state = next(
            arc.nextstate
            for arc in kaldifst.ArcIterator(graph, state)
            if arc.ilabel == label
        )
        next_words = {
            symbols.find(arc.ilabel)
            for arc in kaldifst.ArcIterator(graph, state)
        }
        if next_words != {"o", "oh"}:
            raise RuntimeError(f"{initial!r} has illegal continuations: {sorted(next_words)}")

        for opponent in ("o", "oh"):
            opponent_label = symbols.find(opponent)
            opponent_state = next(
                arc.nextstate
                for arc in kaldifst.ArcIterator(graph, state)
                if arc.ilabel == opponent_label
            )
            if math.isfinite(graph.final(opponent_state).value):
                raise RuntimeError(f"{initial} {opponent} incorrectly accepts an opening-tip command")
            number_words = {
                symbols.find(arc.ilabel)
                for arc in kaldifst.ArcIterator(graph, opponent_state)
            }
            if "twenty" not in number_words or "five" not in number_words:
                raise RuntimeError(
                    f"{initial} {opponent} cannot continue as a turnover: "
                    f"{sorted(number_words)}"
                )


def extract_model(archive: Path, destination: Path) -> Path:
    with tarfile.open(archive, "r:gz") as source:
        source.extractall(destination, filter="data")
    model_dir = destination / "model"
    if not (model_dir / "graph/Gr.fst").is_file():
        raise RuntimeError(f"{archive} does not contain model/graph/Gr.fst")
    return model_dir


def restore_stock_graph(model_dir: Path) -> None:
    # The shipped app model contains only the compact DSL graph. Keep the stock
    # graph separately so a future grammar edit may introduce any word already
    # present in the acoustic model's original vocabulary.
    with gzip.open(STOCK_GRAPH, "rb") as source:
        with (model_dir / "graph/Gr.fst").open("wb") as destination:
            shutil.copyfileobj(source, destination)


def write_archive(model_dir: Path, destination: Path) -> None:
    def normalized(info: tarfile.TarInfo) -> tarfile.TarInfo | None:
        if Path(info.name).name.startswith("._"):
            return None
        info.uid = 0
        info.gid = 0
        info.uname = ""
        info.gname = ""
        info.mtime = 0
        return info

    with destination.open("wb") as raw:
        with gzip.GzipFile(
            filename="", mode="wb", fileobj=raw, compresslevel=9, mtime=0
        ) as compressed:
            with tarfile.open(fileobj=compressed, mode="w") as archive:
                archive.add(model_dir, arcname="model", filter=normalized)


def main() -> None:
    commands, lineup_players = spoken_grammar()
    with tempfile.TemporaryDirectory(prefix="galaxy-voice-model-") as temporary:
        temporary_path = Path(temporary)
        model_dir = extract_model(MODEL_ARCHIVE, temporary_path)
        restore_stock_graph(model_dir)

        graph = compile_graph(model_dir, commands, lineup_players)
        validate_graph_language(graph, commands)
        graph.write(str(model_dir / "graph/Gr.fst"))

        # Loading a recognizer forces Vosk to compose HCLr with the new graph.
        validate_model(model_dir)

        staged = temporary_path / MODEL_ARCHIVE.name
        write_archive(model_dir, staged)
        digest = hashlib.sha256(staged.read_bytes()).hexdigest()
        shutil.move(staged, MODEL_ARCHIVE)

    print(
        f"Wrote {MODEL_ARCHIVE} with "
        f"{len(commands) + 4 * math.perm(len(lineup_players), 5)} commands, "
        f"{graph.num_states} states, sha256 {digest}"
    )


if __name__ == "__main__":
    main()
