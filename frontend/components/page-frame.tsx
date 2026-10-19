"use client";

import { useCallback, useEffect, useRef, useState } from "react";

export type PageFrameProps = {
  html: string;
  title: string;
  mode: "edit" | "public" | "thumb";
  className?: string;
  onReady?: (frame: HTMLIFrameElement) => void;
  onSubmit?: (form: HTMLFormElement, data: FormData) => void;
  onNext?: () => void;
};

/** One isolated document for the editor, public page, and thumbnails. */
export function PageFrame({ html, title, mode, className = "", onReady, onSubmit, onNext }: PageFrameProps) {
  const frameRef = useRef<HTMLIFrameElement>(null);
  const [height, setHeight] = useState(480);
  const onReadyRef = useRef(onReady);
  const onSubmitRef = useRef(onSubmit);
  const onNextRef = useRef(onNext);
  onReadyRef.current = onReady;
  onSubmitRef.current = onSubmit;
  onNextRef.current = onNext;

  const connect = useCallback(() => {
    const frame = frameRef.current;
    const doc = frame?.contentDocument;
    if (!frame || !doc?.body) return;
    const resize = () => setHeight(Math.max(1, doc.documentElement.scrollHeight, doc.body.scrollHeight));
    resize();
    const observer = new ResizeObserver(resize);
    observer.observe(doc.documentElement);
    observer.observe(doc.body);
    const images = Array.from(doc.images);
    images.forEach(image => image.addEventListener("load", resize));
    const submit = (event: Event) => {
      const form = event.target;
      if (!form || (form as Element).tagName !== "FORM" || !(form as Element).matches('[data-sillage="form"]')) return;
      event.preventDefault();
      if (mode !== "public" || !onSubmitRef.current) return;
      onSubmitRef.current(form as HTMLFormElement, new FormData(form as HTMLFormElement));
    };
    doc.addEventListener("submit", submit);
    const next = (event: MouseEvent) => {
      const target = event.target;
      if (!(target as Element | null)?.closest?.("[data-sillage-next]")) return;
      if (mode !== "public" || !onNextRef.current) return;
      event.preventDefault();
      onNextRef.current();
    };
    doc.addEventListener("click", next);
    onReadyRef.current?.(frame);
    return () => {
      observer.disconnect();
      images.forEach(image => image.removeEventListener("load", resize));
      doc.removeEventListener("submit", submit);
      doc.removeEventListener("click", next);
    };
  }, [mode]);

  useEffect(() => {
    const frame = frameRef.current;
    if (!frame) return;
    let cleanup: (() => void) | undefined;
    const loaded = () => { cleanup?.(); cleanup = connect(); };
    frame.addEventListener("load", loaded);
    if (frame.contentDocument?.readyState === "complete") loaded();
    return () => { frame.removeEventListener("load", loaded); cleanup?.(); };
  }, [connect, html]);

  return <iframe
    ref={frameRef}
    title={title}
    srcDoc={html}
    sandbox="allow-forms allow-same-origin"
    className={`page-frame page-frame-${mode} ${className}`}
    style={{ height }}
    tabIndex={mode === "thumb" ? -1 : undefined}
  />;
}
