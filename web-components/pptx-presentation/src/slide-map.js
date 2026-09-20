export function createVisibleSlideMap(slides, slideCount) {
  const count = Number.isSafeInteger(slideCount) && slideCount > 0 ? slideCount : 0;
  const physical = Array.from({ length: count }, (_, index) => index);
  if (!Array.isArray(slides) || slides.length < count) return physical;
  return physical.filter(index => slides[index]?.hidden !== true);
}
