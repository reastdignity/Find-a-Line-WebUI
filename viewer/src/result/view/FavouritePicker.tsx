// The favourite button of a line's details with its folders (as a browser's "bookmark this page"): a
// click opens the user's folders; picking one marks the line there, or moves it there when it is a
// favourite already; "New folder" makes one in the folder highlighted and saves the line into it;
// "Remove" unmarks it. Today's list's star (LinesTable) adds to the last folder used without asking. The result view's
// details (SpotActions.tsx) draw its button as the kit's star icon (`icon`) and follow its opening (`onOpen`); its list's
// star (SpotList.tsx RowStar, the user's gate-2 answer 13 a) mounts it open at the press (`opened`) with the row's own
// class on its button (`buttonClass`).

import { useState } from "preact/hooks";
import { t } from "../../i18n";
import { Button, IconButton } from "../../ui/components";
import { Icon } from "../../ui/icons";
import { FOLDER_DEPTH_MAX } from "../../folders";
import type { Line } from "../../types";
import type { ResultModel } from "../model";
import { cx, Popover, useModel } from "./common";

export interface FavouritePickerProps {
  model: ResultModel;
  line: Line;
  /** The button as the kit's star icon (filled for a favourite) with the worded button's name and title, its folders
   *  opening under it towards the left (the result view: the star at the right end of the details' head). */
  icon?: boolean;
  /** Told when the folders open and close (a phone's sheet rises for them). */
  onOpen?(open: boolean): void;
  /** Mounted with its folders open (a press made before it was drawn: the list's star). */
  opened?: boolean;
  /** More classes for the icon button (the list's star: `vl-star`), and its place in the tab order (the list's star:
   *  -1, reached by the list's arrows). */
  buttonClass?: string;
  buttonTabIndex?: number;
}

export function FavouritePicker({model, line, icon, onOpen, opened = false, buttonClass, buttonTabIndex}: FavouritePickerProps) {
  useModel(model);
  const [open, setOpenState] = useState(opened);
  const setOpen = (v: boolean) => {
    if (v !== open) onOpen?.(v);
    setOpenState(v);
  };
  const [naming, setNaming] = useState(false);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const tree = model.tree, folder = model.folderOf(line), favourite = folder !== undefined;
  const here = favourite ? folder : model.lastFolder;  // highlighted: where it is, or where it would go
  const where = favourite ? (folder === null ? t("ui.picker.top") : tree.path(folder)) : "";

  const pick = (to: number | null) => {
    setOpen(false);
    setNaming(false);
    model.saveTo(line, to);
  };
  const create = async () => {
    const parent = here !== null && tree.depth(here) < FOLDER_DEPTH_MAX ? here : null;
    if (!name.trim() || busy) return;
    setBusy(true);
    const id = await model.newFolder(name, parent);
    setBusy(false);
    if (id === null) return;
    setName("");
    pick(id);
  };
  const remove = () => {
    setOpen(false);
    if (favourite) model.toggleFavourite(line);
  };
  const row = (id: number | null, label: string, depth: number) =>
    <li key={id ?? "top"}>
      <button type="button" class={cx("u-item r-folder", id === here && "u-on")} aria-current={id === folder ? "true" : undefined}
              style={{paddingLeft: `${8 + 14 * depth}px`}} onClick={() => pick(id)}>
        <Icon name={id === null ? "star" : "folder"} /><span class="u-grow">{label}</span>
        {id === folder && <Icon name="check" />}</button></li>;

  const title = favourite ? t("ui.picker.in", {where}) : t("ui.picker.add"), named = t(favourite ? "ui.picker.favourite" : "ui.picker.add");
  return <Popover label={t("ui.picker.label")} open={open} align={icon ? "right" : "left"}
                  onOpen={(v) => { setOpen(v); if (!v) setNaming(false); }}
                  button={(on, toggle) => icon
                    ? <IconButton icon="star" label={named} title={title} plain fav={favourite} expanded={on}
                                  class={cx("r-fav", favourite && "r-on", buttonClass)} tabIndex={buttonTabIndex} onClick={toggle} />
                    : <Button class={cx("r-fav", favourite && "r-on")} aria-expanded={on} onClick={toggle} title={title}>
                      <Icon name="star" fav={favourite} />{named}
                      <Icon name="down" /></Button>}>
    {() => <div class="r-picker">
      <b class="u-h4">{t(favourite ? "ui.picker.move" : "ui.picker.save")}</b>
      <ul class="r-folders" role="list">
        {row(null, t("ui.picker.top_level"), 0)}
        {tree.flat().map(({folder: f, depth}) => row(f.id, f.name, depth))}
      </ul>
      {naming
        ? <form class="r-newfolder" onSubmit={(e) => { e.preventDefault(); create(); }}>
            <input class="u-input" value={name} placeholder={t("ui.picker.name")} aria-label={t("ui.picker.new_name")} maxLength={100}
                   ref={(el) => el?.focus()} onInput={(e) => setName(e.currentTarget.value)}
                   onKeyDown={(e) => { if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); setNaming(false); } }} />
            <Button kind="primary" type="submit" disabled={!name.trim() || busy}>{t("ui.picker.create")}</Button>
          </form>
        : <Button kind="ghost" icon="plus" onClick={() => setNaming(true)}>
            {here !== null ? t("ui.picker.new_in", {name: tree.byId.get(here)?.name ?? ""}) : t("ui.picker.new")}</Button>}
      {favourite && <Button kind="danger" class="r-unfav" onClick={remove}>{t("ui.picker.remove")}</Button>}
    </div>}
  </Popover>;
}
