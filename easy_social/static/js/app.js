(function () {
  function mediaKind(file) {
    if (file.type.startsWith("image/")) {
      return "image";
    }
    if (file.type.startsWith("video/")) {
      return "video";
    }

    const extension = file.name.split(".").pop().toLowerCase();
    if (["gif", "jpg", "jpeg", "png", "webp"].includes(extension)) {
      return "image";
    }
    if (["mov", "mp4", "ogg", "webm"].includes(extension)) {
      return "video";
    }
    return "";
  }

  function clearPreview(preview, frame, name, input, state) {
    if (state.objectUrl) {
      URL.revokeObjectURL(state.objectUrl);
      state.objectUrl = "";
    }
    frame.replaceChildren();
    name.textContent = "";
    preview.hidden = true;
    if (input) {
      input.value = "";
    }
  }

  function setupComposer(composer) {
    const input = composer.querySelector("[data-media-input]");
    const preview = composer.querySelector("[data-media-preview]");
    const frame = composer.querySelector("[data-media-preview-frame]");
    const name = composer.querySelector("[data-media-preview-name]");
    const clear = composer.querySelector("[data-media-preview-clear]");
    const pollToggle = composer.querySelector("[data-poll-toggle]");
    const pollPanel = composer.querySelector("[data-poll-panel]");
    const postTypeInput = composer.querySelector("[data-post-type-input]");
    const pollInputs = Array.from(composer.querySelectorAll("[data-poll-option-input]"));

    if (!input || !preview || !frame || !name || !clear) {
      return;
    }

    const state = { objectUrl: "" };

    function setPollEnabled(enabled) {
      if (!pollToggle || !pollPanel || !postTypeInput || pollInputs.length < 2) {
        return;
      }

      postTypeInput.value = enabled ? "poll" : "text";
      pollPanel.hidden = !enabled;
      pollToggle.setAttribute("aria-pressed", enabled ? "true" : "false");
      pollToggle.textContent = enabled ? "Remove poll" : "Add poll";

      pollInputs.forEach(function (pollInput, index) {
        pollInput.disabled = !enabled;
        pollInput.required = enabled && index < 2;
        if (!enabled) {
          pollInput.value = "";
        }
      });

      if (enabled) {
        pollInputs[0].focus();
      }
    }

    input.addEventListener("change", function () {
      const file = input.files && input.files[0];
      clearPreview(preview, frame, name, null, state);

      if (!file) {
        return;
      }

      const kind = mediaKind(file);
      if (!kind) {
        return;
      }

      state.objectUrl = URL.createObjectURL(file);
      const element = document.createElement(kind === "image" ? "img" : "video");
      element.className = "composer-preview-media";
      element.src = state.objectUrl;

      if (kind === "image") {
        element.alt = "Selected image preview";
      } else {
        element.controls = true;
        element.muted = true;
        element.preload = "metadata";
      }

      frame.replaceChildren(element);
      name.textContent = file.name;
      preview.hidden = false;
    });

    clear.addEventListener("click", function () {
      clearPreview(preview, frame, name, input, state);
      input.dispatchEvent(new Event("change", { bubbles: true }));
    });

    if (pollToggle && pollPanel && postTypeInput && pollInputs.length >= 2) {
      pollToggle.addEventListener("click", function () {
        setPollEnabled(pollPanel.hidden);
      });
      composer.addEventListener("submit", function () {
        if (postTypeInput.value !== "poll") {
          return;
        }

        pollInputs.forEach(function (pollInput, index) {
          if (index >= 2 && !pollInput.value.trim()) {
            pollInput.disabled = true;
          }
        });
      });
      setPollEnabled(false);
    }
  }

  function setupPollCard(card) {
    const forms = Array.from(card.querySelectorAll("[data-poll-option-form]"));
    const totalVotes = card.querySelector("[data-poll-total-votes]");
    const state = card.querySelector("[data-poll-state]");

    if (!forms.length) {
      return;
    }

    function unlockForms() {
      forms.forEach(function (form) {
        const button = form.querySelector("button[type='submit']");
        if (button) {
          button.disabled = false;
        }
      });
    }

    async function submitVote(form) {
      const response = await fetch(form.action, {
        method: "POST",
        body: new FormData(form),
        headers: {
          Accept: "application/json",
        },
      });

      const payload = await response.json().catch(function () {
        return null;
      });

      if (!response.ok) {
        throw new Error((payload && payload.error) || "Unable to vote on this poll.");
      }

      card.dataset.hasVoted = "true";

      if (totalVotes) {
        totalVotes.textContent = String(payload.total_votes);
      }

      if (state) {
        state.textContent = `${payload.total_votes} total votes`;
      }

      const optionLookup = new Map(payload.options.map(function (option) {
        return [String(option.id), option];
      }));

      forms.forEach(function (optionForm) {
        const optionId = optionForm.dataset.optionId;
        const optionData = optionLookup.get(String(optionId));
        const button = optionForm.querySelector("button[type='submit']");
        const result = optionForm.querySelector("[data-poll-option-results]");
        const votes = optionForm.querySelector("[data-poll-option-votes]");
        const percentage = optionForm.querySelector("[data-poll-option-percentage]");

        if (button) {
          button.disabled = true;
          button.classList.toggle("is-selected", String(payload.voted_option_id) === String(optionId));
        }

        if (result) {
          result.hidden = false;
        }

        if (optionData) {
          if (votes) {
            votes.textContent = String(optionData.votes);
          }
          if (percentage) {
            percentage.textContent = String(optionData.percentage);
          }
        }
      });
    }

    forms.forEach(function (form) {
      form.addEventListener("submit", async function (event) {
        event.preventDefault();

        const button = form.querySelector("button[type='submit']");
        if (button) {
          button.disabled = true;
        }

        try {
          await submitVote(form);
        } catch (error) {
          unlockForms();
          window.alert(error.message || "Unable to vote on this poll.");
        }
      });
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("form.composer").forEach(setupComposer);
    document.querySelectorAll("[data-poll-card]").forEach(setupPollCard);
  });
})();
