/*
 * Where the live page looks for the game.
 *
 * Fill this in with the URL `npx wrangler deploy` printed for the worker in
 * worker/ and commit it, so nobody has to type anything. It is not a secret --
 * viewers can only read, and the write key never leaves the scorekeeper's phone.
 *
 * Leaving it empty is fine too: the page then asks for the URL once and keeps it
 * in that device's browser storage. A ?api= query parameter overrides both.
 */
window.GALAXY_LIVE = {
  endpoint: ""
};
