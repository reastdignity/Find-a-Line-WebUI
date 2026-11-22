// The notice after a sign-in (the public site): an early beta, what the lines do not account for, and
// how to report problems (GitHub issues, the site's e-mail, Report a problem). web.py's sign-in leaves
// the cookie WELCOME for a few minutes; the page shows the notice once and deletes it. A native
// <dialog> (showModal: Esc, the focus kept in it, the page behind inert).

import { useEffect, useRef, useState } from "preact/hooks";
import { Button } from "../ui/components";
import { Icon, Logo } from "../ui/icons";
import { canReport, ISSUES_URL, openReport, siteContact } from "../report";
import { t } from "../i18n";
import { Rich } from "../ui/Intro";
import "./notices.css";

const WELCOME = "__Host-findaline-welcome";  // web.WELCOME_COOKIE

function welcomed(): boolean {
  return document.cookie.split(";").some((c) => c.trim().startsWith(WELCOME + "="));
}

function forget() {
  document.cookie = `${WELCOME}=; Max-Age=0; Path=/; Secure; SameSite=Lax`;
}

/** The contact as a link: mailto: for an e-mail address, the address of a web page, else text. */
function Contact({contact}: {contact: string}) {
  if (/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(contact)) return <a href={`mailto:${contact}`}>{contact}</a>;
  if (/^https:\/\//.test(contact)) return <a href={contact} target="_blank" rel="noopener">{contact}</a>;
  return <>{contact}</>;
}

export function BetaNotice() {
  const ref = useRef<HTMLDialogElement>(null);
  const [shown] = useState(() => canReport() && welcomed());
  useEffect(() => {
    if (!shown) return;
    forget();
    ref.current?.showModal();
  }, []);
  if (!shown) return null;
  const contact = siteContact();
  const close = () => ref.current?.close();
  return <dialog ref={ref} class="ui u-dialog n-beta" aria-labelledby="n-beta-title">
    <div class="n-head"><Logo /><span class="u-badge">{t("ui.beta.badge")}</span></div>
    <h2 class="u-h" id="n-beta-title">{t("ui.beta.title")}</h2>
    <p>{t("ui.beta.young")}</p>
    <p class="n-warn"><Icon name="warn" /><span><Rich text={t("ui.beta.main")} /></span></p>
    <p>{t("ui.beta.tell")}</p>
    <ul>
      <li>{t("ui.beta.lines")}</li>
      <li>{t("ui.beta.water")}</li>
      <li>{t("ui.beta.bugs")}</li>
    </ul>
    <p class="n-ways">
      <a href={ISSUES_URL} target="_blank" rel="noopener"><Icon name="link" />{t("ui.beta.issues")}</a>
      {contact && <span><Icon name="info" />{`${t("ui.beta.email")} `}<Contact contact={contact} /></span>}
      <button type="button" class="u-link" onClick={() => { close(); openReport(); }}>
        <Icon name="warn" />{t("ui.beta.report")}</button>
    </p>
    <p class="u-small">{t("ui.beta.later")}</p>
    <div class="n-actions"><Button kind="primary" onClick={close}>{t("ui.beta.ok")}</Button></div>
  </dialog>;
}
