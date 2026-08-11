"""Install a certificate the customer already has — Ploi's "install existing certificate".

Let's Encrypt covers most sites, and the ones it does not are exactly the ones somebody has
already paid for: a wildcard from a registrar, an organisation-validated certificate a client
insists on, or a Cloudflare origin certificate (extremely common, and Let's Encrypt cannot
issue one because the domain resolves to Cloudflare).

Three things shape the whole module.

**The private key is the most sensitive thing a customer will ever paste into ServerAlly.**
It never touches a command line — not as an argument, not through a heredoc — because an
argument is visible in `ps` while the command runs and is kept in the stored output of the
run. It travels over SFTP, and the shell only ever handles what carries no value: the
permissions, the config edit, the reload. It is never stored in our database and never
logged.

**Everything that can be checked is checked before the server is touched at all.** A key that
does not match its certificate makes nginx refuse to start — which takes down every site on
the machine, not just this one. A certificate for the wrong domain gives every visitor a name
warning, which is worse than no HTTPS because it looks handled. Both are decidable here, from
the pasted text, with no server involved, so both are refused at the door.

**A pasted certificate does not renew itself.** That is the honest trade against Let's
Encrypt and it is said plainly rather than discovered a year later. Our expiry monitoring
watches the live certificate, so it does warn — but the renewal is the owner's job.
"""
from __future__ import annotations

import datetime as _dt
import logging
import shlex

logger = logging.getLogger(__name__)


class CertError(Exception):
    """Something we refuse to install, in words worth showing the customer."""


#: Where an installed certificate lives. Its own directory per site, so replacing one can
#: never disturb another, and outside any web root by construction.
BASE_DIR = "/etc/ssl/serverally"

_PEM_CERT = "-----BEGIN CERTIFICATE-----"
_KEY_MARKS = ("-----BEGIN PRIVATE KEY-----", "-----BEGIN RSA PRIVATE KEY-----",
              "-----BEGIN EC PRIVATE KEY-----", "-----BEGIN ENCRYPTED PRIVATE KEY-----")


def paths_for(domain: str) -> dict:
    """The three files, derived from the domain — never from anything a caller sends.

    A path built from caller text is a path that can point at `/etc/shadow`.
    """
    from app.services import ssl_service

    safe = ssl_service.valid_name(domain)     # refuses anything that is not a hostname
    root = f"{BASE_DIR}/{safe}"
    return {"dir": root, "cert": f"{root}/fullchain.pem", "key": f"{root}/privkey.pem"}


# ── What was pasted ──────────────────────────────────────────────────────────

def _load_chain(pem: str) -> list:
    from cryptography import x509

    blocks, current = [], []
    for line in (pem or "").splitlines():
        current.append(line)
        if "END CERTIFICATE" in line:
            blocks.append("\n".join(current) + "\n")
            current = []
    out = []
    for block in blocks:
        try:
            out.append(x509.load_pem_x509_certificate(block.encode()))
        except Exception as exc:  # noqa: BLE001 — every parse failure is one message
            raise CertError(
                "That certificate could not be read. Paste the whole thing, including the "
                "-----BEGIN CERTIFICATE----- and -----END CERTIFICATE----- lines."
            ) from exc
    if not out:
        raise CertError(
            "That does not look like a certificate. It should start with "
            "-----BEGIN CERTIFICATE----- and end with -----END CERTIFICATE-----.")
    return out


def _load_key(pem: str):
    from cryptography.hazmat.primitives.serialization import load_pem_private_key

    text = (pem or "").strip()
    if _PEM_CERT in text:
        # The single most likely paste mistake, and worth naming precisely: somebody puts the
        # certificate in both boxes. "Could not be read" would send them looking at the key.
        raise CertError("That is a certificate, not a private key. The private key is a "
                        "separate file, usually ending in .key.")
    if not any(m in text for m in _KEY_MARKS):
        raise CertError("That does not look like a private key. It should start with "
                        "-----BEGIN PRIVATE KEY----- or -----BEGIN RSA PRIVATE KEY-----.")
    try:
        return load_pem_private_key(text.encode(), password=None)
    except TypeError as exc:
        # A passphrase-protected key would make nginx prompt for it at every start, which on
        # a server means it simply never starts.
        raise CertError(
            "That private key is protected by a passphrase. nginx cannot ask for one when it "
            "starts, so remove it first: openssl rsa -in your.key -out unlocked.key"
        ) from exc
    except Exception as exc:  # noqa: BLE001
        raise CertError("That private key could not be read. Paste the whole file, including "
                        "the BEGIN and END lines.") from exc


def cert_names(cert) -> list[str]:
    """Every name this certificate is valid for — the SANs, falling back to the subject.

    Modern browsers ignore the common name entirely, so the SAN list is the real answer; the
    fallback only exists so an ancient certificate produces a useful message rather than
    "covers nothing".
    """
    from cryptography import x509
    from cryptography.x509.oid import NameOID

    try:
        san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName)
        names = [n.lower() for n in san.value.get_values_for_type(x509.DNSName)]
        if names:
            return names
    except x509.ExtensionNotFound:
        pass
    return [a.value.lower() for a in cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
            if isinstance(a.value, str)]


def covers(names: list[str], domain: str) -> bool:
    """Does this certificate cover that domain, wildcards included?

    A wildcard matches exactly one label: `*.shop.com` covers `www.shop.com` and does NOT
    cover `a.b.shop.com` or the bare `shop.com`. Getting that wrong in the generous direction
    would let us install a certificate that browsers then reject.
    """
    want = (domain or "").strip().lower().rstrip(".")
    for name in names:
        if name == want:
            return True
        if name.startswith("*."):
            suffix = name[1:]                      # ".shop.com"
            if want.endswith(suffix) and "." not in want[: -len(suffix)]:
                return True
    return False


def check(cert_pem: str, key_pem: str, domain: str, *, now: _dt.datetime | None = None) -> dict:
    """Everything decidable without the server. Raises `CertError` on anything we refuse.

    Returns what the screen should show back: the names it covers, who issued it, when it
    expires, and whether the chain looks complete.
    """
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

    chain = _load_chain(cert_pem)
    key = _load_key(key_pem)
    leaf = chain[0]

    # 1. The key must belong to the certificate. Without this nginx refuses to start, and on
    #    a shared server that takes down every site on it — not only this one.
    def _pub(k):
        return k.public_bytes(Encoding.DER, PublicFormat.SubjectPublicKeyInfo)

    if _pub(key.public_key()) != _pub(leaf.public_key()):
        raise CertError("That private key does not belong to that certificate. They have to "
                        "be the pair that was issued together.")

    # 2. It must cover this site, or every visitor gets a name warning — which is worse than
    #    no HTTPS, because the padlock says it was handled.
    names = cert_names(leaf)
    if not covers(names, domain):
        raise CertError(
            f"That certificate is for {', '.join(names) or 'no domain we can read'} — not for "
            f"{domain}. Installing it would show every visitor a security warning.")

    # 3. Dates. An expired certificate is strictly worse than none: the browser refuses the
    #    page outright instead of marking it insecure.
    now = now or _dt.datetime.now(_dt.timezone.utc)
    not_after = leaf.not_valid_after_utc
    not_before = leaf.not_valid_before_utc
    if not_after <= now:
        raise CertError(f"That certificate expired on {not_after:%-d %B %Y}. An expired "
                        f"certificate stops the site loading altogether.")
    if not_before > now:
        raise CertError(f"That certificate is not valid until {not_before:%-d %B %Y}. "
                        f"Browsers would reject it until then.")

    issuer = next((a.value for a in leaf.issuer if isinstance(a.value, str)), "unknown")
    return {
        "names": names,
        "issuer": issuer,
        "expires": not_after.date().isoformat(),
        "days_left": (not_after - now).days,
        # Said, not enforced: a self-signed or origin certificate legitimately has no chain,
        # and a missing intermediate is a warning worth showing rather than a refusal.
        "chain_length": len(chain),
        "self_signed": leaf.issuer == leaf.subject,
    }


def normalise_chain(cert_pem: str) -> str:
    """One PEM holding the leaf first, then anything else that was pasted with it.

    nginx wants leaf-then-intermediates in a single file, and pasting them the other way
    round is a common mistake that produces a certificate browsers reject on some devices
    and accept on others — the worst kind of failure to diagnose.
    """
    from cryptography.hazmat.primitives.serialization import Encoding

    chain = _load_chain(cert_pem)
    leaf = chain[0]
    rest = chain[1:]
    # If the "leaf" is actually a CA and something later is not, the paste was reversed.
    if len(chain) > 1 and _is_ca(leaf) and not _is_ca(chain[-1]):
        leaf, rest = chain[-1], chain[:-1]
    return b"".join(c.public_bytes(Encoding.PEM) for c in [leaf, *rest]).decode()


def _is_ca(cert) -> bool:
    from cryptography import x509

    try:
        return bool(cert.extensions.get_extension_for_class(x509.BasicConstraints).value.ca)
    except x509.ExtensionNotFound:
        return False


# ── Putting it on the server ─────────────────────────────────────────────────

#: The configuration edit, as a plain script rather than an f-string.
#:
#: It is kept out of the surrounding f-string deliberately: doubling every brace in a regex
#: to smuggle it through `.format()` is how the first version acquired a bug I could not see
#: by reading it. Its three arguments are paths we built ourselves.
_EDIT_PY = r'''
import re, sys

path, cert, key = sys.argv[1], sys.argv[2], sys.argv[3]
text = open(path).read()

if re.search(r'^\s*ssl_certificate\s', text, re.M):
    # Already serving HTTPS — repoint EVERY block. A site whose http and https halves use
    # different certificates is a bug nobody can see from one screen.
    text = re.sub(r'^([ \t]*)ssl_certificate\s+[^;]+;',
                  lambda m: m.group(1) + 'ssl_certificate ' + cert + ';', text, flags=re.M)
    text = re.sub(r'^([ \t]*)ssl_certificate_key\s+[^;]+;',
                  lambda m: m.group(1) + 'ssl_certificate_key ' + key + ';', text, flags=re.M)
elif re.search(r'^\s*SSLCertificateFile\s', text, re.M):
    text = re.sub(r'^([ \t]*)SSLCertificateFile\s+\S+',
                  lambda m: m.group(1) + 'SSLCertificateFile ' + cert, text, flags=re.M)
    text = re.sub(r'^([ \t]*)SSLCertificateKeyFile\s+\S+',
                  lambda m: m.group(1) + 'SSLCertificateKeyFile ' + key, text, flags=re.M)
else:
    # No HTTPS yet. Rather than writing a second server block — which means duplicating the
    # root, the index and the PHP handler, and getting one of them wrong — the SAME block
    # gains a 443 listener. One block, both schemes, nothing duplicated.
    #
    # Once per BLOCK, not once per matching line. An ordinary vhost has both `listen 80;`
    # and `listen [::]:80;`, and inserting after each of them gives nginx a duplicate
    # listener, which makes it refuse to start — for every site on the machine.
    out, depth, block_at, added_here, added = [], 0, None, False, 0
    for line in text.splitlines():
        out.append(line)
        if block_at is None and re.match(r'^\s*server\s*\{', line):
            block_at, added_here = depth, False
        if block_at is not None and not added_here:
            m = re.match(r'^([ \t]*)listen\s+(?:\[::\]:)?80\b[^;]*;', line)
            if m:
                pad = m.group(1)
                out += [pad + 'listen 443 ssl;', pad + 'listen [::]:443 ssl;',
                        pad + 'ssl_certificate ' + cert + ';',
                        pad + 'ssl_certificate_key ' + key + ';']
                added_here, added = True, added + 1
        depth += line.count('{') - line.count('}')
        if block_at is not None and depth <= block_at:
            block_at = None
    if not added:
        print("no listener to add HTTPS to")
        sys.exit(1)
    text = "\n".join(out) + "\n"

open(path, 'w').write(text)
'''


# ── A certificate signing request ────────────────────────────────────────────
#
# Ploi's "create signing request". The other half of installing a certificate you bought: a
# commercial authority will not issue one until you send them a CSR, and a CSR is only
# meaningful together with the private key it was generated from.
#
# **Both are generated ON THE SERVER, and the key never leaves it.** Generating them here
# would mean the private key passing through our process and our database — and the whole
# reason the install path uses SFTP is that a private key should touch as little as possible.
# The CSR itself is public by design (it is what you email to the authority), so reading that
# back is safe.

#: Where the pending pair waits between asking for a certificate and receiving one. Its own
#: names, so a request in progress can never be mistaken for a live certificate.
CSR_KEY = "request-key.pem"
CSR_FILE = "request.csr"

#: What an authority asks for. Only the domain is required — everything else is optional and
#: only a commercial (organisation-validated) certificate actually needs it.
_SUBJECT_FIELDS = ("country", "state", "locality", "organisation", "unit")

#: These end up between `/` and `=` in openssl's own subject syntax, where either character
#: would silently start a new field. Refused rather than escaped, the same rule the domain
#: follows.
_BAD_SUBJECT = set("/=\n\r\\\"\'`$;|&<>")


def check_subject(fields: dict) -> dict:
    """Tidy and bound what goes into the certificate's subject."""
    out: dict[str, str] = {}
    for key in _SUBJECT_FIELDS:
        value = " ".join(str(fields.get(key) or "").split())
        if not value:
            continue
        if set(value) & _BAD_SUBJECT:
            raise CertError(
                f"Remove / = and quotes from the {key} — they separate the fields inside a "
                f"certificate, so they cannot be part of one.")
        if key == "country":
            value = value.upper()
            if len(value) != 2 or not value.isalpha():
                raise CertError("The country has to be a two-letter code, like GB or BD.")
        elif len(value) > 64:
            raise CertError(f"The {key} is too long — 64 characters at most.")
        out[key] = value
    return out


def subject_string(domain: str, fields: dict) -> str:
    """openssl's `-subj`. The domain is validated by `valid_name`, never escaped.

    Checks the fields itself rather than trusting the caller to have done it: a second entry
    point that skips the validation is how the validation stops happening.
    """
    from app.services import ssl_service

    fields = check_subject(fields)
    parts = []
    for key, letter in (("country", "C"), ("state", "ST"), ("locality", "L"),
                        ("organisation", "O"), ("unit", "OU")):
        if fields.get(key):
            parts.append(f"{letter}={fields[key]}")
    # CN last, because it is the one field that must be there and reading it at the end of
    # the line is how everybody checks a CSR.
    parts.append(f"CN={ssl_service.valid_name(domain)}")
    return "/" + "/".join(parts)


def build_csr_command(domain: str, fields: dict, *, names: list[str] | None = None) -> str:
    """Generate a private key and a signing request, and print the request.

    The key is written mode 600 and stays here. The request is printed, because that is the
    thing the customer copies into their certificate authority's form.

    Every name the site answers to goes in as a SAN, for the same reason the Let's Encrypt
    path covers them: a certificate that does not name `www` gives half the visitors a
    browser warning on a site whose owner has been told it is secure.
    """
    from app.services import ssl_service

    subject = subject_string(domain, fields)
    p = paths_for(domain)
    key = shlex.quote(f"{p['dir']}/{CSR_KEY}")
    csr = shlex.quote(f"{p['dir']}/{CSR_FILE}")

    wanted = ssl_service.names_for(domain, names)
    san = ",".join(f"DNS:{ssl_service.valid_name(n)}" for n in wanted)

    return f"""
set -u
install -d -m 700 -o root -g root {shlex.quote(p["dir"])}
command -v openssl >/dev/null 2>&1 || {{ echo ">>> ERROR: openssl is not installed"; exit 1; }}

# -nodes: no passphrase. nginx cannot be asked for one when it starts, so a protected key
# means the web server simply never comes up.
if ! openssl req -new -newkey rsa:2048 -nodes \\
     -keyout {key} -out {csr} \\
     -subj {shlex.quote(subject)} \\
     -addext {shlex.quote("subjectAltName=" + san)} >/tmp/sa_csr.log 2>&1; then
  echo ">>> ERROR: the signing request could not be created"
  sed -n '1,10p' /tmp/sa_csr.log
  rm -f {key} {csr} /tmp/sa_csr.log
  exit 1
fi
rm -f /tmp/sa_csr.log
chmod 600 {key}; chown root:root {key}
chmod 644 {csr}
echo ">>> CSR"
cat {csr}
""".strip()


def build_pending_key_check(domain: str) -> str:
    """Is there a key waiting from a signing request made here?

    Read as a fact rather than remembered: the request may have been made weeks ago, and a
    file on the server is the only thing that actually decides it.
    """
    p = paths_for(domain)
    return (f'[ -f {shlex.quote(p["dir"] + "/" + CSR_KEY)} ] '
            f'&& echo "pending=yes" || echo "pending=no"')


def build_use_pending_key(domain: str) -> str:
    """Move the signing request's key into place as the certificate's key.

    This is what makes "create a request, then install what comes back" work without the
    private key ever leaving the server or being typed by anybody.
    """
    p = paths_for(domain)
    src = shlex.quote(f"{p['dir']}/{CSR_KEY}")
    dst = shlex.quote(p["key"] + ".new")
    return (f'set -u; [ -f {src} ] || {{ echo "missing"; exit 1; }}; '
            f'cp -p {src} {dst}; chmod 600 {dst}; echo "ready"')


def parse_csr(output: str) -> str:
    """The request itself, out of the command's output."""
    text = output or ""
    head, tail = "-----BEGIN CERTIFICATE REQUEST-----", "-----END CERTIFICATE REQUEST-----"
    start, end = text.find(head), text.find(tail)
    if start < 0 or end < 0:
        raise CertError("The signing request could not be created on this server.")
    return text[start:end + len(tail)] + "\n"


def build_prepare_command(domain: str) -> str:
    """Make the directory the two files are about to be uploaded into.

    SFTP does not create parent directories, and on a site's FIRST certificate this folder
    does not exist — so without this the upload fails before anything else has a chance to.
    Mode 700 while the key is landing: for the moment between the upload and the `chmod 600`
    that follows, the directory itself is what keeps the key out of other users' reach.
    """
    return f"install -d -m 700 -o root -g root {shlex.quote(paths_for(domain)['dir'])}"


def build_install_command(config_path: str, domain: str, *, apache: bool = False) -> str:
    """Point the site's configuration at the files, then prove the site still works.

    The certificate and the key are already on the server by the time this runs — written
    over SFTP, so nothing secret is ever an argument here. This command only moves them into
    place with the right permissions and edits the config.

    Same discipline as every other config write in this codebase: keep a copy, make the web
    server ACCEPT the new file before reloading, confirm the site still answers with real
    content, and restore the copy on any failure. A configuration that does not parse does
    not break one site — the reload fails for the whole machine.
    """
    p = paths_for(domain)
    cfg = shlex.quote(config_path)
    cert, key, tmp_cert, tmp_key = (shlex.quote(p["cert"]), shlex.quote(p["key"]),
                                    shlex.quote(p["cert"] + ".new"),
                                    shlex.quote(p["key"] + ".new"))
    host = shlex.quote(domain)
    tester = "apachectl configtest" if apache else "nginx -t"
    reload_cmd = ("(systemctl reload apache2 2>/dev/null || systemctl reload httpd 2>/dev/null "
                  "|| apachectl graceful)") if apache else \
                 "(systemctl reload nginx 2>/dev/null || nginx -s reload)"

    return f"""
set -u
CFG={cfg}
BAK="$CFG.serverally-cert-$(date +%s)"

# What the site was doing BEFORE we touched it. A site that was already broken must not have
# its outage blamed on this change and the certificate ripped back out — that would leave
# somebody unable to install a certificate at exactly the moment they are fixing the site.
WAS=$(curl -so /dev/null -w '%{{http_code}}' --max-time 8 "http://{host}/" || echo 000)


cp -p "$CFG" "$BAK" || {{ echo ">>> ERROR: could not back up the configuration"; exit 1; }}

# Keep the certificate that is there now too. Replacing one on a site that already has HTTPS
# means the live paths are overwritten BEFORE the config is known to be good — so without
# this, a refused config would leave the running site pointing at a file we swapped under it.
# 700, not 755: the web server reads the key as root before it drops privileges, so
# nothing else needs to get into this folder.
install -d -m 700 {shlex.quote(p["dir"])}
[ -f {cert} ] && cp -p {cert} {cert}.prev
[ -f {key} ] && cp -p {key} {key}.prev

restore() {{
  cp -p "$BAK" "$CFG"
  [ -f {cert}.prev ] && mv {cert}.prev {cert}
  [ -f {key}.prev ] && mv {key}.prev {key}
  rm -f "$BAK" {cert}.prev {key}.prev
}}

# The key is readable by root only. It is the one file here whose exposure would matter.
mv {tmp_cert} {cert} && chmod 644 {cert} && chown root:root {cert}
mv {tmp_key} {key} && chmod 600 {key} && chown root:root {key}

python3 - "$CFG" {cert} {key} <<'PYEOF' || {{ echo ">>> ERROR: the configuration could not be updated"; exit 1; }}
{_EDIT_PY}
PYEOF

if ! {tester} >/tmp/sa_cert_test.log 2>&1; then
  restore
  echo ">>> ERROR: the web server refused the new configuration; nothing was changed"
  sed -n '1,20p' /tmp/sa_cert_test.log
  exit 1
fi

{reload_cmd} >/dev/null 2>&1 || true
sleep 1

# Content, not a status code. A site can answer 200 with a blank body or an error page, and
# a certificate that "installed" onto a broken site is not a success.
BODY=$(curl -sk --max-time 12 "https://{host}/" | head -c 2000)
CODE=$(curl -sko /dev/null -w '%{{http_code}}' --max-time 12 "https://{host}/")
if [ -z "$BODY" ] || [ "$CODE" = "000" ] || [ "${{CODE#5}}" != "$CODE" ]; then
  if [ "$WAS" = "000" ] || [ "${{WAS#5}}" != "$WAS" ]; then
    # It was already not serving before this ran. The certificate is not the cause and
    # taking it back out would not fix anything — so it stays, and we say so.
    rm -f "$BAK" {cert}.prev {key}.prev
    echo ">>> OK-BROKEN: $CODE"
    exit 0
  fi
  restore
  {tester} >/dev/null 2>&1 && {reload_cmd} >/dev/null 2>&1
  echo ">>> ERROR: the site stopped serving after the change (HTTP $CODE), so it was put back"
  exit 1
fi

rm -f "$BAK" {cert}.prev {key}.prev
echo ">>> OK: $CODE"
""".strip()


def explain(code: int, output: str) -> tuple[bool, str]:
    """What the customer reads. Never the script's last line — ours, keyed off the marker."""
    text = output or ""
    if code == 0 and ">>> OK-BROKEN" in text:
        return True, ("The certificate is installed. The site itself was already not "
                      "loading before this ran, so that is a separate problem to fix — "
                      "the certificate was left in place because removing it would not "
                      "help.")
    if code == 0 and ">>> OK" in text:
        return True, "The certificate is installed and the site is serving over HTTPS."
    for marker, message in (
        ("could not back up",
         "The site's configuration could not be backed up, so nothing was changed."),
        ("refused the new configuration",
         "The web server refused the new configuration, so nothing was changed. The "
         "certificate files were written but are not in use."),
        ("stopped serving",
         "The site stopped answering after the change, so the previous configuration was put "
         "back. The certificate was not applied."),
        ("no listener to add HTTPS to",
         "This site's configuration has no plain-HTTP listener to add HTTPS to. Its "
         "configuration may be hand-written — edit it from the Manage screen."),
        ("could not be updated",
         "The site's configuration could not be updated, so nothing was changed."),
    ):
        if marker in text:
            return False, message
    return False, "The certificate could not be installed, and nothing was changed."
