(function () {
  'use strict';

  if (window.parent === window || !document.referrer) return;

  let parentOrigin;
  try {
    const referrer = new URL(document.referrer);
    const isProduction = referrer.origin === 'https://lab.ugatta-llc.com';
    const isLocalPreview = referrer.hostname === '127.0.0.1' || referrer.hostname === 'localhost';
    if (!isProduction && !isLocalPreview) return;
    parentOrigin = referrer.origin;
  } catch (error) {
    return;
  }

  let lastHeight = 0;
  let scheduled = false;

  function reportHeight() {
    scheduled = false;
    const height = document.body ? Math.ceil(Array.from(document.body.children).reduce(function (bottom, element) {
      return Math.max(bottom, element.getBoundingClientRect().bottom + window.scrollY);
    }, 0)) : 0;
    if (height < 320 || height === lastHeight) return;
    lastHeight = height;
    window.parent.postMessage({
      source: 'tourism-market-signal',
      type: 'resize',
      height: height
    }, parentOrigin);
  }

  function scheduleHeightReport() {
    if (scheduled) return;
    scheduled = true;
    window.requestAnimationFrame(reportHeight);
  }

  window.addEventListener('load', scheduleHeightReport);
  window.addEventListener('pageshow', scheduleHeightReport);
  window.addEventListener('resize', scheduleHeightReport);

  if (document.fonts && document.fonts.ready) {
    document.fonts.ready.then(scheduleHeightReport);
  }

  if (typeof ResizeObserver === 'function') {
    const observer = new ResizeObserver(scheduleHeightReport);
    observer.observe(document.documentElement);
  }

  scheduleHeightReport();
})();
