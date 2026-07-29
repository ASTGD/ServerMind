"""Mail health — the invisible failures, and never inventing one.

Three of the four real causes of "my email goes to spam" produce no error anywhere: two
SPF records, too many SPF lookups, and a DMARC policy that only watches. Those get the
most attention here. The other half of the job is restraint — a false alarm about email
sends a customer chasing a problem that does not exist, and costs more than a missed one.
"""
from __future__ import annotations

import pytest

from app.services import mail_service as m


# ── the failure nobody finds on their own ────────────────────────────────────
def test_two_spf_records_mean_the_domain_has_none():
    """Both records look correct. The standard says a receiver must discard every one, so
    the domain is unprotected while appearing configured."""
    f = m.evaluate_spf(["v=spf1 include:one.example -all",
                        "v=spf1 include:two.example -all"])
    assert len(f) == 1 and f[0].severity == "critical"
    assert "ignore all of them" in f[0].title
    assert "Delete all but one" in f[0].fix


def test_one_spf_record_is_fine():
    assert m.evaluate_spf(["v=spf1 include:one.example -all"]) == []


def test_no_spf_at_all_is_serious():
    f = m.evaluate_spf([])
    assert f[0].key == "spf_missing" and f[0].severity == "critical"


def test_other_txt_records_are_not_mistaken_for_spf():
    """A domain has many TXT records — verification tokens, DKIM, anything."""
    assert m.evaluate_spf(["google-site-verification=abc",
                           "v=spf1 include:one.example -all"]) == []


# ── the lookup limit, which is invisible until mail stops ────────────────────
@pytest.mark.parametrize("record,expected", [
    ("v=spf1 -all", 0),
    ("v=spf1 ip4:1.2.3.4 -all", 0),                       # addresses cost nothing
    ("v=spf1 include:a.com -all", 1),
    ("v=spf1 a mx -all", 2),
    ("v=spf1 include:a.com include:b.com a:mail.c.com -all", 3),
    ("v=spf1 redirect=other.com", 1),
    ("v=spf1 exists:%{i}.a.com -all", 1),
    ("v=spf1 ptr -all", 1),
    ("v=spf1 ~include:a.com -all", 1),                     # qualifier does not hide it
])
def test_counting_what_each_record_costs(record, expected):
    assert m.spf_lookup_count(record) == expected


def test_going_over_the_limit_discards_the_whole_record():
    record = "v=spf1 " + " ".join(f"include:s{i}.example" for i in range(11)) + " -all"
    f = m.evaluate_spf([record])
    assert any(x.key == "spf_lookups" and x.severity == "critical" for x in f)
    assert "thrown away" in next(x for x in f if x.key == "spf_lookups").detail


def test_sitting_exactly_on_the_limit_is_a_warning_not_a_failure():
    """It works today and breaks the moment one more service is added, with no error."""
    record = "v=spf1 " + " ".join(f"include:s{i}.example" for i in range(10)) + " -all"
    f = m.evaluate_spf([record])
    assert any(x.key == "spf_lookups_near" and x.severity == "warning" for x in f)


def test_a_normal_record_raises_nothing_about_lookups():
    f = m.evaluate_spf(["v=spf1 include:_spf.google.com include:sendgrid.net ~all"])
    assert not any("lookup" in x.key for x in f)


# ── records that look like protection and are not ────────────────────────────
def test_allowing_everyone_is_treated_as_serious():
    f = m.evaluate_spf(["v=spf1 include:a.com +all"])
    assert any(x.key == "spf_permissive" and x.severity == "critical" for x in f)


def test_a_bare_all_is_the_same_thing():
    assert any(x.key == "spf_permissive" for x in m.evaluate_spf(["v=spf1 a mx all"]))


def test_a_neutral_ending_is_a_warning():
    assert any(x.key == "spf_neutral" for x in m.evaluate_spf(["v=spf1 a ?all"]))


@pytest.mark.parametrize("ending", ["-all", "~all"])
def test_the_two_sensible_endings_raise_nothing(ending):
    assert m.evaluate_spf([f"v=spf1 include:a.com {ending}"]) == []


def test_dmarc_that_only_watches_is_named_as_such():
    f = m.evaluate_dmarc("v=DMARC1; p=none; rua=mailto:a@b.com")
    assert f[0].key == "dmarc_monitor_only"
    assert "right place to start and the wrong place to stay" in f[0].detail


@pytest.mark.parametrize("policy", ["quarantine", "reject"])
def test_a_dmarc_policy_that_acts_raises_nothing(policy):
    assert m.evaluate_dmarc(f"v=DMARC1; p={policy}; rua=mailto:a@b.com") == []


def test_no_dmarc_is_a_warning_not_a_failure():
    """Missing DMARC does not stop mail arriving; it only leaves forgery unhandled."""
    f = m.evaluate_dmarc(None)
    assert f[0].severity == "warning"


def test_a_dmarc_record_with_no_policy_is_flagged():
    assert m.evaluate_dmarc("v=DMARC1; rua=mailto:a@b.com")[0].key == "dmarc_malformed"


# ── restraint: never invent a problem ────────────────────────────────────────
def test_a_missing_dkim_is_reported_as_not_found_never_as_absent():
    """The selector is chosen by whoever set the mail up, so a missing answer proves
    nothing. Saying "you have no DKIM" would send a customer to fix what is not broken."""
    f = m.evaluate_dkim(None)
    assert f[0].key == "dkim_unknown"
    assert "Could not find" in f[0].title
    for wrong in ("no DKIM", "missing DKIM", "you have none"):
        assert wrong.lower() not in (f[0].title + f[0].detail).lower()


def test_a_found_dkim_selector_raises_nothing():
    assert m.evaluate_dkim("default") == []


def test_a_domain_that_only_hosts_a_website_is_not_told_its_email_is_broken():
    """No MX is normal for most domains. Reporting it as a fault would make the check
    noise on the majority of what an agency manages."""
    f = m.evaluate_mx([])
    assert f[0].severity == "info"
    assert "fine if" in f[0].detail


def test_a_domain_that_receives_mail_raises_nothing():
    assert m.evaluate_mx(["mail.example.com"]) == []


def test_no_blocklist_hits_means_nothing_is_said():
    assert m.evaluate_blocklists([], "1.2.3.4") == []


def test_being_blocklisted_says_what_it_means_and_what_causes_it():
    f = m.evaluate_blocklists(["Spamhaus"], "203.0.113.9")
    assert f[0].severity == "critical"
    assert "203.0.113.9" in f[0].detail
    assert "hacked website" in f[0].fix, "name the usual cause, not just the symptom"


# ── the whole picture ────────────────────────────────────────────────────────
def _health(findings):
    h = m.MailHealth(domain="example.com")
    h.findings = findings
    return h


def test_the_verdict_follows_the_worst_thing_found():
    assert _health([]).verdict == "ok"
    assert _health(m.evaluate_dmarc(None)).verdict == "at risk"
    assert _health(m.evaluate_spf([])).verdict == "failing"


def test_an_informational_note_does_not_make_a_domain_look_broken():
    """A website-only domain has an info finding and must still read as fine."""
    assert _health(m.evaluate_mx([])).verdict == "ok"


def test_the_score_moves_with_what_is_wrong():
    assert _health([]).score == 100
    assert _health(m.evaluate_spf([])).score == 70
    assert 0 <= _health(m.evaluate_spf([]) + m.evaluate_dmarc(None)).score <= 100


def test_the_score_never_leaves_its_range():
    many = m.evaluate_spf([]) * 10
    assert _health(many).score == 0


def test_the_summary_is_a_sentence_a_non_expert_reads():
    bad = _health(m.evaluate_spf([]))
    assert "reject" in m.summarise(bad) or "spam" in m.summarise(bad)
    assert m.summarise(_health([])).endswith("is set up correctly.")


# ── alerting: worse is news, the same is not ─────────────────────────────────
def test_only_getting_worse_is_worth_an_email():
    assert m.should_alert("ok", "failing")
    assert m.should_alert("ok", "at risk")
    assert m.should_alert("at risk", "failing")


def test_staying_bad_does_not_email_again():
    """A domain at risk for a month must not email daily, or the one that matters is
    filtered out with the rest."""
    assert not m.should_alert("failing", "failing")
    assert not m.should_alert("at risk", "at risk")


def test_recovering_is_silent_but_re_arms():
    assert not m.should_alert("failing", "ok")
    assert m.should_alert("ok", "failing"), "and it can alert again next time"


def test_nothing_known_yet_still_alerts_on_a_real_problem():
    assert m.should_alert(None, "failing")
    assert not m.should_alert(None, "ok")


# ── the blocklist list itself ────────────────────────────────────────────────
def test_only_well_established_blocklists_are_used():
    """Several public lists are abandoned and answer "listed" to everything. A long list
    is worse than a short one: it would report healthy mail as blocked."""
    assert len(m.BLOCKLISTS) <= 4
    names = {label for _zone, label in m.BLOCKLISTS}
    assert "Spamhaus" in names


# ── the false positive that nearly shipped ───────────────────────────────────
@pytest.mark.parametrize("answers,expected", [
    (["127.0.0.2"], "listed"),          # the standard "you are on this list"
    (["127.0.0.4"], "listed"),
    (["127.0.0.11"], "listed"),
    ([], "clean"),                      # no record at all is the clean answer
    (["127.255.255.254"], "refused"),   # "we will not answer you" — NOT a listing
    (["127.255.255.252"], "refused"),
    (["10.0.0.1"], "refused"),          # anything outside 127.0.0.0/8 is not an answer
])
def test_a_blocklists_reply_is_read_by_its_meaning_not_its_existence(answers, expected):
    """Caught by running it against real domains: Spamhaus answers 127.255.255.254 to
    queries from shared resolvers, meaning "refused". Treating any reply as a listing
    reported Google and GitHub as blocklisted — which would have told nearly every
    customer their mail was blocked, and destroyed trust in every other alert we send."""
    assert m.classify_blocklist_answer(answers) == expected


def test_a_refused_lookup_is_never_reported_as_a_listing():
    assert m.evaluate_blocklists([], "1.2.3.4", unchecked=["Spamhaus"]) == []


def test_being_unable_to_check_any_list_is_said_out_loud():
    """Silence there would be a false all-clear."""
    f = m.evaluate_blocklists([], "1.2.3.4",
                              unchecked=[label for _z, label in m.BLOCKLISTS])
    assert f and f[0].key == "blocklist_unchecked" and f[0].severity == "info"
    assert "not a sign of a problem" in f[0].detail


def test_one_refused_list_out_of_three_is_not_worth_mentioning():
    assert m.evaluate_blocklists([], "1.2.3.4", unchecked=["Spamhaus"]) == []


def test_a_real_listing_still_reports_even_when_another_list_refused():
    f = m.evaluate_blocklists(["SpamCop"], "1.2.3.4", unchecked=["Spamhaus"])
    assert f[0].severity == "critical" and "SpamCop" in f[0].detail
