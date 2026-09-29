"""Explain collaboration surfaces from the current tool selection, without granting tools."""
from misaka.core.wiring import KINDS

SESSION_KINDS = KINDS

SISTER_TOOLS = {
    "SendMessage": ("Consult `last-order` or a registered Sister ID about evidence, methods, progress or dependencies. "
                    "A name reaches the one session of that role in your space; with several there, address one "
                    "by its card or session id. Delivery is asynchronous and may wake a contact session. "
                    "Owned sub-agent IDs/names are resolved before those names. "
                    "Ordinary messages do not create, start, complete or park a card."),
    "misaka_sister_view": "Read a registered Sister's introduction to choose a collaborator.",
    "misaka_board": "Check this project's actual task-card states and ownership.",
    "misaka_card": "Create a scoped assignment with testable acceptance criteria; creation does not start work.",
    "misaka_dispatch": "Start approved ready cards; select task IDs to avoid dispatching unrelated ready work.",
    "misaka_sister": "Start one approved ready card, not a new Sister identity or generic sub-agent.",
    "misaka_sister_message": ("Address an existing card by task ID and current generation to steer or continue its session. "
                              "Reply to a parked card's help request here, not through SendMessage; "
                              "observe the tool's confirmation requirement for completed tasks."),
    "misaka_sister_output": "Read or wait for a card's result, then assess its evidence, deliverables and acceptance criteria.",
    "misaka_sister_peek": "Inspect recent output for diagnosis, not as proof of completion or acceptance.",
    "misaka_sister_stop": "Stop the identified task through its lifecycle control, not by sending a conversational request.",
    "misaka_pane_list": "See the panes in your tab of the panel and which of them may be closed.",
    "misaka_pane_close": ("Close what finished cards left in your tab; a pane running a card is stopped with "
                          "misaka_sister_stop, and a pane the user opened is closed only at their request."),
    "misaka_card_link": "Record a real dependency between existing task cards.",
    "misaka_card_request_review": "Configure a different Sister as an independent reviewer before work starts.",
    "misaka_card_review": "Record the independent review decision and actionable feedback through the review contract.",
    "misaka_my_card": "Read your card's current contract, dependency and review state.",
    "misaka_card_note": "Keep findings, evidence and unresolved questions on the card, not only in messages.",
    "misaka_card_complete": "Declare the card finished only when its contract deliverable exists; a turn without it leaves the card running.",
    "misaka_research_assign": ("Submit or revise this phase's research plan -- its cards and, in a node's first plan, "
                               "its forks; recording it is not a launch receipt."),
    "misaka_research_start": ("Record the user's explicit go-ahead for the pending research plan or reconciliation "
                              "through its owning session."),
    "misaka_research_dispose": ("Answer every material red-team issue of this node: revise, rebut, concede, covered, "
                                "park or branch; corrections stay in the node."),
    "misaka_research_decide": "Record the forks this node opens and why the alternatives not taken are not opened.",
    "misaka_research_reconcile": ("Reconcile the research graph at a level: open options as nodes, join finished "
                                  "nodes, record options not pursued and relations between nodes."),
    "misaka_research_dissolve": ("Record that a conclusion dissolves a question rather than answering it; dissolving "
                                 "the research question waits for the user's consent."),
    "misaka_research_consent": ("Record the user's decision on dissolving the research question, once they have "
                                "decided in conversation."),
    "misaka_research_relate": "Record connections between research nodes that the survey brings to light.",
    "misaka_research_withdraw": "Withdraw the pending research round when the user chooses to conclude without it.",
    "misaka_research_skip": "Skip the current research node only when the user chooses that outcome.",
    "misaka_research_retry": "Run a failed research node again without waiting for the level to end.",
}

SUBAGENT_TOOLS = {
    "Agent": "Delegate a bounded task to an available task-specific agent definition.",
    "TaskOutput": "Read or wait for an existing background task when its result is needed.",
    "TaskStop": "Stop an existing running task.",
}


def collaboration_sections(active):
    """Keep capability catalogs and parameter documentation in the tool definitions."""
    active = set(active)
    sections = []
    sisters = [name for name in SISTER_TOOLS if name in active]
    if sisters:
        lines = [
            "## Last Order / Sister coordination",
            ("Use messages for consultation and coordination, and task contracts for formal assignments. "
             "A message, a recorded plan, a launch receipt and an accepted result are different events. "
             "Use only tools enabled in this session, following their current approval and completion contracts."),
            *(f"- `{name}`: {SISTER_TOOLS[name]}" for name in sisters),
        ]
        if any(name.startswith("misaka_research_") for name in sisters):
            lines.append("In Research, the driver creates and launches the planned cards after the applicable phase gate. "
                         "Do not duplicate those assignments through ordinary board tools or messages.")
        sections.append("\n".join(lines))
    subagents = [name for name in SUBAGENT_TOOLS if name in active]
    if subagents:
        lines = ["## Sub-agents"]
        if "Agent" in active:
            lines += [
                ("Sisters are registered, persistent domain experts. Sub-agents are task-specific workers "
                 "launched from this session, not Sister identities."),
                ("Use the Agent tool's current description for available agent definitions and their scopes; "
                 "do not use a Sister number as subagent_type. Delegate useful, bounded work and remain "
                 "responsible for evaluating and integrating the results."),
            ]
        else:
            lines.append("Only existing-task management is available here; these tools do not grant "
                         "the ability to launch a new sub-agent.")
        lines.extend(f"- `{name}`: {SUBAGENT_TOOLS[name]}" for name in subagents)
        if "SendMessage" in active:
            lines.append("- `SendMessage`: Continue a sub-agent owned by this session using its agent ID or "
                         "registered name; keep their names distinct from role names.")
        lines.append("Verify delegated evidence before citing it. Do not present a launch receipt as a completed result.")
        sections.append("\n".join(lines))
    return sections


class CollaborationPart:
    def __init__(self):
        self.tools = []
        self.commands = []
        self.session = None
        self._published = ""
        self._input = None

    def attach(self, session):
        self.session = session

    async def before_agent_start(self, event, _ctx):
        original = event["systemPrompt"]
        # A caller may pass our previous output, optionally followed by other parts.
        # Verify its original prefix and owned position: identical text elsewhere
        # may belong to a user's persona and must not be removed from a fresh base.
        previous = self._input + self._published if self._input is not None and self._published else None
        prompt = (self._input + original[len(previous):]
                  if previous is not None and original.startswith(previous) else original)
        self._input = prompt
        sections = collaboration_sections(self.session.getActiveToolNames())
        self._published = "\n\n" + "\n\n".join(sections) if sections else ""
        prompt += self._published
        return {"systemPrompt": prompt} if prompt != original else None


def part(_spec):
    return CollaborationPart()
