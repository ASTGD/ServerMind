import type { CloudInstance } from "@/api/cloud"

/**
 * How an instance being imported will actually be reached, and therefore whether this import
 * has to ask for a login at all.
 *
 * **This is the browser's copy of a rule the backend also applies** (`cloud_service.
 * transport_for` / `credential_needed`), and it exists so the form and the endpoint agree.
 * Without it the button happily submits a batch the API then refuses with a 422, and the
 * customer is left working out which of their choices caused it.
 *
 * The rule itself, and the reason it is this way round: **Systems Manager is the fallback,
 * not the default.** It has no file transfer and no interactive terminal yet, so picking it
 * for a machine that has a perfectly good address would quietly hand over a server with no
 * File Manager, no `.env` editor, no certificate install and no terminal — a downgrade nobody
 * asked for. So an address wins, unless the customer says otherwise; and what it unlocks is
 * the case SSH cannot do at all, an instance with no address we can reach.
 */
export interface ImportChoices {
  /** Use Systems Manager wherever it is available, not only where there is no address. */
  preferSsm: boolean
  /** The customer asked to connect over the private address. */
  usePrivateIp: boolean
}

/** The address this import would connect to, or nothing when there is none. */
export function addressFor(i: CloudInstance, choices: ImportChoices): string | null {
  return (choices.usePrivateIp ? i.private_ip : (i.public_ip ?? i.private_ip)) ?? null
}

/** Whether this instance will be reached through Systems Manager. */
export function viaSsm(i: CloudInstance, choices: ImportChoices): boolean {
  if (!i.ssm_managed) return false          // ticking the box cannot conjure an agent
  return choices.preferSsm || !addressFor(i, choices)
}

/** Whether this instance can be imported at all. */
export function importable(i: CloudInstance, choices: ImportChoices): boolean {
  return Boolean(addressFor(i, choices)) || Boolean(i.ssm_managed)
}

/**
 * Whether a username and key still have to be supplied.
 *
 * False for a batch that is entirely Systems Manager — asking anyway would be asking for the
 * exact artefact SSM exists to remove.
 */
export function needsLogin(chosen: CloudInstance[], choices: ImportChoices): boolean {
  return chosen.some((i) => !viaSsm(i, choices))
}

/** How many of the chosen will use Systems Manager — for saying so before they commit. */
export function ssmCount(chosen: CloudInstance[], choices: ImportChoices): number {
  return chosen.filter((i) => viaSsm(i, choices)).length
}
