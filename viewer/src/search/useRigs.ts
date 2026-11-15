// The user's saved rigs (/api/rigs: with the account on the public site, in the local app's jobs.sqlite) and
// the rig in use, which this browser keeps (findaline.rig in localStorage: the id; spec-search 1.3, U-5): a
// missing or unknown id takes the first rig when the rigs load, no rig the starting rig (basic.ts STARTING_RIG).
// A rig in use that goes later (deleted on another device, found when a refused change reloads the list) is
// "lost": the first rig stands in for Basic, but nothing is saved into it before the user chooses a rig.

import { useCallback, useEffect, useState } from "preact/hooks";
import { api } from "../app/api";
import { RIG_FIELDS, rigInUse, STARTING_RIG, storedRigId, storeRigId, type Rig, type RigValues } from "./basic";

export const RIGS_MAX = 10;  // jobs.RIGS_MAX, until the server says (/api/rigs "max")

/** A rig of the server's answer with its seven values as numbers. */
const asRig = (r: {id: number; name: string; values: Record<string, number>}): Rig =>
  ({id: r.id, name: r.name, values: Object.fromEntries(RIG_FIELDS.map((k) => [k, Number(r.values[k])])) as RigValues});

export interface RigsState {
  rigs: Rig[];
  max: number;
  loaded: boolean;           // the first answer came (or failed)
  error: string;             // of loading
  inUse: Rig | null;         // null: the starting rig
  /** The rig in use went after the rigs loaded (deleted on another device): the first rig stands in for Basic,
   *  but nothing is saved into it before the user chooses a rig. */
  lost: boolean;
  values: RigValues;         // the rig in use's values (the starting rig's without one)
  choose(id: number): void;
  /** A new rig, then in use; throws the server's error (ApiError). */
  add(name: string, values: RigValues): Promise<Rig>;
  /** Rename a rig and/or change its values; throws the server's error. */
  change(id: number, change: {name?: string; values?: RigValues}): Promise<void>;
  /** Delete a rig; the rig in use gone, the first takes its place. */
  remove(id: number): Promise<void>;
}

/** The saved rigs and the rig in use, loaded once. */
export function useRigs(): RigsState {
  const [rigs, setRigs] = useState<Rig[]>([]);
  const [max, setMax] = useState(RIGS_MAX);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState("");
  // The id of the rig in use on this page: the stored one when the rigs load (else the first), then the user's
  // choices; a reload that no longer lists it leaves it as it is (lost)
  const [current, setCurrent] = useState<number | null>(null);

  const reload = useCallback(async () => {
    const answer = await api.rigs();
    const list = answer.rigs.map(asRig);
    setRigs(list);
    setMax(answer.max);
    return list;
  }, []);
  useEffect(() => {
    reload().then((list) => { setCurrent(rigInUse(list, storedRigId())?.id ?? null); setError(""); },
                  (e: Error) => setError(e.message)).finally(() => setLoaded(true));
  }, [reload]);

  const lost = current !== null && !rigs.some((r) => r.id === current);
  const inUse = rigInUse(rigs, current);
  const choose = (id: number | null) => { setCurrent(id); storeRigId(id); };
  /** A change refused (a rig deleted on another device: "rig_missing", a name taken there): the list as the
   *  server has it now, then the error for the caller to show. */
  const refused = async (e: unknown): Promise<never> => {
    await reload().catch(() => undefined);
    throw e;
  };
  return {
    rigs, max, loaded, error, inUse, lost, values: inUse ? inUse.values : STARTING_RIG, choose,
    add: async (name, values) => {
      const {id} = await api.addRig(name, values).catch(refused);
      choose(id);
      const list = await reload();
      return list.find((r) => r.id === id) ?? {id, name, values};
    },
    change: async (id, change) => {
      await api.changeRig(id, change).catch(refused);
      await reload();
    },
    remove: async (id) => {
      await api.deleteRig(id).catch(refused);
      const list = await reload();
      if (inUse?.id === id) choose(list[0]?.id ?? null);
    },
  };
}
