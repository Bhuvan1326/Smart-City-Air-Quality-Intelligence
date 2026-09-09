export function makeFakeIndexedDB() {
  const stores = {
    "pending-evidence": new Map(),
    "cached-actions": new Map(),
    "auth-context": new Map(),
  };

  function makeReq(work) {
    const req = { result: undefined, error: undefined, onsuccess: null, onerror: null };
    queueMicrotask(() => {
      try {
        req.result = work();
        if (req.onsuccess) req.onsuccess({ target: req });
      } catch (e) {
        req.error = e;
        if (req.onerror) req.onerror({ target: req });
      }
    });
    return req;
  }

  function makeStore(name) {
    const map = stores[name];
    return {
      get: (key) => makeReq(() => map.get(key)),
      getAll: () => makeReq(() => Array.from(map.values())),
      put: (val) => makeReq(() => { map.set(val.id ?? val.key, val); return val.id ?? val.key; }),
      delete: (key) => makeReq(() => { map.delete(key); }),
      openCursor: () => makeReq(() => null),
    };
  }

  function makeTx(names) {
    const tx = { oncomplete: null, onerror: null, error: undefined };
    const list = Array.isArray(names) ? names : [names];
    tx.objectStore = (n) => makeStore(n);
    queueMicrotask(() => queueMicrotask(() => { if (tx.oncomplete) tx.oncomplete(); }));
    return tx;
  }

  return {
    open: (name, version) => {
      const req = { result: undefined, onsuccess: null, onerror: null, onupgradeneeded: null };
      queueMicrotask(() => {
        req.result = {
          objectStoreNames: { contains: (n) => true },
          transaction: (names) => makeTx(names),
          close: () => {},
        };
        if (req.onsuccess) req.onsuccess({ target: req });
      });
      return req;
    },
    __stores: stores,
  };
}
