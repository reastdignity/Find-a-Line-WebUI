// result/model.ts with the rows' reader of the tests (rows.ts), for the Node units that bundle "result/model": their
// made-up runs are data.js's value (a head and its rows) and other runs lines.js's, which ResultModel here reads into
// columns first (runData, lineColumns), as the page's model took them before store wave 4's item 5.
import { ResultModel as Model, type ResultOptions } from "../src/result/model";
import type { RunData, RunInfo } from "../src/types";
import { lineColumns, runData, type RunLines, type RunScript } from "./rows";

export * from "../src/types";
export * from "../src/result/model";
export * from "./rows";

export class ResultModel extends Model {
  constructor(data: RunData | RunScript, options: ResultOptions = {}) {
    super("columns" in data ? data : runData(data), options);
  }

  addRun(info: RunInfo, loaded: RunData | RunLines, color?: string) {
    const data = "columns" in loaded ? loaded
      : {...loaded, columns: lineColumns(loaded.lines, loaded.terrain, loaded.ends)} as unknown as RunData;
    super.addRun(info, data, color);
  }
}
