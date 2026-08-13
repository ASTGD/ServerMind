"""PowerShell's std_err is five streams in a trench coat, and four of them are not errors.

Found on the FIRST real command ever run against a live Windows box (Server 2022, WinRM):
a command that succeeded came back with a std_err full of XML. Everything before this had
been tested against mocked pywinrm, and a mock returns whatever the test author imagined —
which is why nobody had seen what PowerShell actually sends.

It was not cosmetic. `execute_stream` yields std_err into the output stream and the playbook
runner emits it to the screen, so every Windows playbook run would have shown a wall of
markup; and several callers treat a non-empty std_err as "something went wrong".

`PROGRESS_FROM_THE_REAL_BOX` below is the exact payload that live server returned, kept
verbatim. An invented sample would only prove the parser handles what I expected.
"""
import pytest

from app.services.winrm_service import _clean_ps_error

# Captured from 23.106.52.144 (Windows Server 2022) on the first command of a fresh session.
PROGRESS_FROM_THE_REAL_BOX = (
    '<Objs Version="1.1.0.1" xmlns="http://schemas.microsoft.com/powershell/2004/04">'
    '<Obj S="progress" RefId="0"><TN RefId="0"><T>System.Management.Automation.PSCustomObject'
    '</T><T>System.Object</T></TN><MS><I64 N="SourceId">1</I64><PR N="Record">'
    '<AV>Preparing modules for first use.</AV><AI>0</AI><Nil /><PI>-1</PI><PC>-1</PC>'
    '<T>Completed</T><SR>-1</SR><SD> </SD></PR></MS></Obj>'
    '<Obj S="progress" RefId="1"><TNRef RefId="0" /><MS><I64 N="SourceId">2</I64>'
    '<PR N="Record"><AV>Preparing modules for first use.</AV><AI>0</AI><Nil /><PI>-1</PI>'
    '<PC>-1</PC><T>Completed</T><SR>-1</SR><SD> </SD></PR></MS></Obj></Objs>'
)


def test_the_payload_that_started_this_becomes_nothing():
    """A command that worked must not report an error. This exact XML arrived on a
    successful `$PSVersionTable` and would have been shown to the customer as std_err."""
    assert _clean_ps_error(PROGRESS_FROM_THE_REAL_BOX) == ""


def test_a_real_error_survives_and_is_readable():
    clixml = (
        '#< CLIXML\n<Objs Version="1.1.0.1" xmlns="http://schemas.microsoft.com/powershell/2004/04">'
        '<S S="Error">nope : The term \'nope\' is not recognized as the name of a cmdlet._x000D__x000A_</S>'
        "</Objs>"
    )
    out = _clean_ps_error(clixml)
    assert "is not recognized as the name of a cmdlet" in out
    assert "<S" not in out and "_x000D_" not in out


def test_an_error_split_across_records_is_joined_into_a_sentence():
    """PowerShell chops one long error into several records. Listed separately they read as
    fragments; the customer is meant to read a sentence."""
    clixml = (
        '<Objs Version="1.1.0.1" xmlns="x">'
        '<S S="Error">Cannot find path </S>'
        "<S S=\"Error\">'C:\\nope' because it does not exist._x000D__x000A_</S>"
        "</Objs>"
    )
    assert _clean_ps_error(clixml) == (
        "Cannot find path 'C:\\nope' because it does not exist."
    )


def test_an_error_hiding_among_progress_records_is_still_found():
    """The realistic case: a first command that also fails. Dropping the noise must not
    drop the news."""
    mixed = PROGRESS_FROM_THE_REAL_BOX.replace(
        "</Objs>", '<S S="Error">Access is denied._x000D__x000A_</S></Objs>')
    assert _clean_ps_error(mixed) == "Access is denied."


def test_warnings_are_kept():
    """A warning is real information. Dropping it would hide something true because it was
    not quite an error."""
    clixml = '<Objs Version="1.1.0.1" xmlns="x"><S S="Warning">Reboot required.</S></Objs>'
    assert _clean_ps_error(clixml) == "Reboot required."


@pytest.mark.parametrize("stream", ["verbose", "debug"])
def test_verbose_and_debug_are_dropped(stream):
    clixml = f'<Objs Version="1.1.0.1" xmlns="x"><S S="{stream}">chatter</S></Objs>'
    assert _clean_ps_error(clixml) == ""


def test_xml_entities_come_back_as_the_characters_they_stand_for():
    """An error about a command containing < or & is common, and showing the customer
    `&lt;` teaches them nothing."""
    clixml = ('<Objs Version="1.1.0.1" xmlns="x">'
              '<S S="Error">Unexpected token &apos;&amp;&apos; in &lt;script&gt;</S></Objs>')
    assert _clean_ps_error(clixml) == "Unexpected token '&' in <script>"


# ── things that are NOT CLIXML must survive untouched ────────────────────────

def test_a_transport_failure_is_passed_through():
    """`WinRM error: …` is written by us when the connection itself fails. A parser built
    for a different shape must not swallow the one message that explains why nothing ran."""
    msg = "WinRM error: (401, 'Unauthorized')"
    assert _clean_ps_error(msg) == msg


def test_plain_text_is_passed_through():
    assert _clean_ps_error("something went wrong") == "something went wrong"


@pytest.mark.parametrize("empty", ["", "   ", None])
def test_empty_stays_empty(empty):
    assert _clean_ps_error(empty) == ""


def test_the_result_never_contains_markup():
    """The property the whole fix exists for: whatever goes in, no XML comes out."""
    for sample in (PROGRESS_FROM_THE_REAL_BOX,
                   PROGRESS_FROM_THE_REAL_BOX.replace(
                       "</Objs>", '<S S="Error">boom</S></Objs>')):
        out = _clean_ps_error(sample)
        assert "<Obj" not in out and "<S " not in out and "xmlns" not in out
