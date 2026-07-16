/**
 * A write that fully replaces the server-side state for a given `id`. Both
 * `PATCH /api/profiles/{id}` (autosave) and `PUT /api/favorites` are of this
 * shape: the request body is the *entire* new state, so a later response
 * clobbers an earlier one regardless of which edit was actually last.
 */
export type SerializedWrite<T> = (id: string, payload: T) => Promise<void>;

interface Deferred {
  promise: Promise<void>;
  resolve: () => void;
  reject: (reason?: unknown) => void;
}

function defer(): Deferred {
  let resolve!: () => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<void>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

/**
 * Wrap a full-replace `write` so that, per `id`, at most one call is ever in
 * flight and a call made while another is running does not start a second
 * concurrent request. Instead it becomes the *pending* payload for that id,
 * replacing any earlier pending payload (trailing coalesce). When the in-flight
 * write settles, the latest pending payload — and only that one — is fired.
 *
 * The server therefore only ever receives one write at a time per id, in causal
 * order; intermediate superseded payloads are dropped rather than raced. This
 * closes the silent lost-update bug where two overlapping full-replace writes
 * let whichever *response* landed last win, regardless of which edit was last.
 *
 * Returned-promise contract for each call:
 *  - The call that actually starts a request settles (resolve/reject) with that
 *    request's result.
 *  - A call that is superseded by a newer call before it ever fires resolves —
 *    it was intentionally dropped because a fresher state replaced it; that is
 *    not a failure.
 */
export function createSingleFlight<T>(write: SerializedWrite<T>): SerializedWrite<T> {
  const inFlight = new Set<string>();
  const pending = new Map<string, { payload: T; deferred: Deferred }>();

  async function drain(id: string): Promise<void> {
    try {
      for (;;) {
        const entry = pending.get(id);
        if (!entry) break;
        pending.delete(id);
        try {
          await write(id, entry.payload);
          entry.deferred.resolve();
        } catch (e) {
          entry.deferred.reject(e);
        }
      }
    } finally {
      inFlight.delete(id);
    }
  }

  return (id, payload) => {
    const prior = pending.get(id);
    if (prior) {
      // Superseded before it ever fired: drop it. Its state is stale, not
      // failed, so resolve rather than reject its awaiter.
      prior.deferred.resolve();
    }
    const deferred = defer();
    pending.set(id, { payload, deferred });
    if (!inFlight.has(id)) {
      inFlight.add(id);
      void drain(id);
    }
    return deferred.promise;
  };
}
