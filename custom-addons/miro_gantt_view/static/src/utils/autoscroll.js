/** @odoo-module **/

/**
 * Checks if the mouse cursor is near the top or bottom edge of the scroll container
 * and, if so, starts auto-scrolling in that direction.
 *
 * @param {Object} renderer - The GanttRenderer instance
 * @param {MouseEvent} ev - The mouse event
 */
export function checkAutoScroll(renderer, ev) {
  const scrollEl = renderer.scrollArea && renderer.scrollArea.el;
  if (!scrollEl) return;
  const rect = scrollEl.getBoundingClientRect();
  const margin = 50;
  if (ev.clientY < rect.top + margin) {
    const dist = ev.clientY - (rect.top + margin);
    setAutoScrollSpeed(renderer, Math.max(-10, dist * 0.2));
  } else if (ev.clientY > rect.bottom - margin) {
    const dist = ev.clientY - (rect.bottom - margin);
    setAutoScrollSpeed(renderer, Math.min(10, dist * 0.2));
  } else {
    setAutoScrollSpeed(renderer, 0);
  }
}

/**
 * Sets the auto-scroll speed and starts/stops the animation frame loop.
 *
 * @param {Object} renderer - The GanttRenderer instance
 * @param {number} speed - Scroll speed in pixels per frame (positive = down, negative = up)
 */
function setAutoScrollSpeed(renderer, speed) {
  if (renderer._autoScrollSpeed === speed) return;
  renderer._autoScrollSpeed = speed;
  if (speed && !renderer._autoScrollRAF) {
    renderer._autoScrollRAF = requestAnimationFrame(() =>
      tickAutoScroll(renderer),
    );
  } else if (!speed && renderer._autoScrollRAF) {
    stopAutoScroll(renderer);
  }
}

/**
 * Animation frame callback for smooth auto-scrolling.
 * Scrolls the body element and accumulates the scroll delta.
 *
 * @param {Object} renderer - The GanttRenderer instance
 */
function tickAutoScroll(renderer) {
  if (!renderer._autoScrollSpeed) {
    renderer._autoScrollRAF = null;
    return;
  }
  const scrollEl = renderer.scrollArea && renderer.scrollArea.el;
  if (scrollEl) {
    const prevScroll = scrollEl.scrollTop;
    scrollEl.scrollTop += renderer._autoScrollSpeed;
    renderer._autoScrollAccum += scrollEl.scrollTop - prevScroll;
    // Keep the drop indicator (and its insertion index / target group) in sync
    // with the content while auto-scrolling, even if the mouse is stationary.
    if (
      renderer._dragState &&
      renderer._dragState.mode === 'move' &&
      renderer._dragLastY != null &&
      typeof renderer._syncDragDropPosition === 'function'
    ) {
      renderer._syncDragDropPosition();
    }
  }
  renderer._autoScrollRAF = requestAnimationFrame(() =>
    tickAutoScroll(renderer),
  );
}

/**
 * Stops auto-scrolling and resets related state variables.
 *
 * @param {Object} renderer - The GanttRenderer instance
 */
export function stopAutoScroll(renderer) {
  if (renderer._autoScrollRAF) {
    cancelAnimationFrame(renderer._autoScrollRAF);
    renderer._autoScrollRAF = null;
  }
  renderer._autoScrollSpeed = 0;
  renderer._autoScrollAccum = 0;
}
