// Logos guide: copy the AI assistant instructions.
(function () {
  var b = document.querySelector("[data-copy-prompt]");
  var pre = document.getElementById("lg-prompt-text");
  if (!b || !pre) return;
  b.addEventListener("click", function () {
    (navigator.clipboard ? navigator.clipboard.writeText(pre.textContent) : Promise.reject()).then(
      function () { b.textContent = "Copied"; },
      function () { b.textContent = "Select the text and copy it"; });
  });
})();
