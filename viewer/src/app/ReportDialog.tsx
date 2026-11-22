// "Report a problem" (the public site): a native <dialog> opened by report.openReport from anywhere in
// the app: the kind of problem, the text, and what is sent with it (the page, the run and line, the
// window's size; the server adds the browser's User-Agent), then "Thank you". POST /api/reports.

import { useEffect, useRef, useState } from "preact/hooks";
import { Button, Segmented, type Option } from "../ui/components";
import { currentContext, REPORT_EVENT, type ReportCategory, type ReportContext, type ReportRequest } from "../report";
import { api } from "./api";
import { t } from "../i18n";
import "./notices.css";

const TEXT_MAX = 4000;  // jobs.REPORT_TEXT_MAX
const CATEGORIES: ReportCategory[] = ["results", "water", "interface", "other"];
/** The kinds of problem with their words (ui.report.category.<kind>); each has its hint (ui.report.hint.<kind>). */
const categories = (): Option<ReportCategory>[] =>
  CATEGORIES.map((value) => ({value, label: t(`ui.report.category.${value}`)}));

export function ReportDialog() {
  const ref = useRef<HTMLDialogElement>(null);
  const [category, setCategory] = useState<ReportCategory>("results");
  const [text, setText] = useState("");
  const [context, setContext] = useState<ReportContext>({});
  const [about, setAbout] = useState("");
  const [state, setState] = useState<"form" | "sending" | "sent">("form");
  const [error, setError] = useState("");

  useEffect(() => {
    const open = (e: Event) => {
      const request = (e as CustomEvent<ReportRequest>).detail || {};
      setCategory(request.category || "results");
      setContext({...currentContext(), ...request.context});
      setAbout(request.about || "");
      setText("");
      setError("");
      setState("form");
      if (!ref.current?.open) ref.current?.showModal();
    };
    window.addEventListener(REPORT_EVENT, open);
    return () => window.removeEventListener(REPORT_EVENT, open);
  }, []);

  const close = () => ref.current?.close();
  const send = async () => {
    if (!text.trim() || state === "sending") return;
    setState("sending");
    setError("");
    try {
      await api.report({category, text, context});
      setState("sent");
    } catch (e: any) {
      setError(e.message);
      setState("form");
    }
  };
  const attached = [
    context.page && t("ui.report.sent_page", {page: context.page}),
    about && t("ui.report.sent_about", {about}),
    context.run && t(context.line ? "ui.report.sent_run_line" : "ui.report.sent_run"),
    context.viewport && t("ui.report.sent_window", {size: context.viewport}),
    t("ui.report.sent_agent"),
  ].filter(Boolean) as string[];

  return <dialog ref={ref} class="ui u-dialog n-report" aria-labelledby="n-report-title">
    {state === "sent" ? <>
      <h2 class="u-h" id="n-report-title">{t("ui.report.thanks")}</h2>
      <p>{t("ui.report.sent")}</p>
      <div class="n-actions"><Button kind="primary" onClick={close}>{t("ui.common.close")}</Button></div>
    </> : <form method="dialog" onSubmit={(e) => { e.preventDefault(); send(); }}>
      <h2 class="u-h" id="n-report-title">{t("ui.report.title")}</h2>
      <Segmented label={t("ui.report.kind")} options={categories()} value={category} onChange={setCategory} />
      <label class="n-field"><span class="u-small">{t(`ui.report.hint.${category}`)}</span>
        <textarea class="u-input n-text" rows={7} maxLength={TEXT_MAX} value={text} aria-label={t("ui.report.text")}
                  onInput={(e) => setText(e.currentTarget.value)} />
        <span class="u-small n-count">{text.length} / {TEXT_MAX}</span></label>
      <div class="u-small n-attached"><b>{t("ui.report.sent_with")}</b> {attached.join(", ")}.</div>
      {error && <p class="c-error n-error" role="alert">{error}</p>}
      <div class="n-actions">
        <Button kind="ghost" onClick={close}>{t("ui.common.cancel")}</Button>
        <Button kind="primary" type="submit" disabled={!text.trim() || state === "sending"}>
          {t(state === "sending" ? "ui.report.sending" : "ui.report.send")}</Button>
      </div>
    </form>}
  </dialog>;
}

/** The notice after a sign-in and the report's dialog: what app.tsx mounts with the interface. */
export { BetaNotice } from "./BetaNotice";
