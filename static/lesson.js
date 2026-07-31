// AI Code Helper chat — lesson page

const chatMessages = document.getElementById("chat-messages");
const chatForm = document.getElementById("chat-form");
const chatText = document.getElementById("chat-text");
const sendBtn = document.getElementById("send-btn");
const fileInput = document.getElementById("screenshot-input");
const attachPreview = document.getElementById("attach-preview");
const attachThumb = document.getElementById("attach-thumb");
const attachRemove = document.getElementById("attach-remove");

const ALLOWED_IMAGE_TYPES = ["image/png", "image/jpeg", "image/gif", "image/webp"];

// Text-only transcript sent back to the server so the AI remembers the conversation.
const history = [];

// Logged-in users get their saved chats for this lesson loaded from the database.
if (typeof IS_LOGGED_IN !== "undefined" && IS_LOGGED_IN) {
  loadSavedChats();
}

async function loadSavedChats() {
  try {
    const res = await fetch(`/api/chat-history/${LESSON_ID}`);
    if (!res.ok) return;
    const data = await res.json();
    if (!data.history || !data.history.length) return;

    const divider = document.createElement("div");
    divider.className = "chat-divider";
    divider.textContent = "Your previous chats";
    chatMessages.appendChild(divider);

    for (const msg of data.history) {
      const imageURL = msg.has_screenshot ? `/api/chat-upload/${msg.id}` : null;
      if (msg.user_message || imageURL) {
        addMessage("user", msg.user_message, imageURL);
      }
      if (msg.assistant_reply) {
        addMessage("ai", msg.assistant_reply);
      }
      history.push({
        role: "user",
        content: (msg.has_screenshot ? "[uploaded a screenshot of my Scratch code] " : "") +
          (msg.user_message || "What's wrong with my code?"),
      });
      history.push({ role: "assistant", content: msg.assistant_reply });
    }
  } catch {
    // If history can't load, the chat still works — just starts fresh.
  }
}

let attachedFile = null;
let attachedURL = null;

function setAttachment(file) {
  attachedFile = file;
  if (attachedURL) URL.revokeObjectURL(attachedURL);
  attachedURL = URL.createObjectURL(file);
  attachThumb.src = attachedURL;
  attachPreview.classList.remove("hidden");
}

fileInput.addEventListener("change", () => {
  const file = fileInput.files[0];
  if (file) setAttachment(file);
});

attachRemove.addEventListener("click", clearAttachment);

// Paste image support
document.addEventListener("paste", (e) => {
  const items = e.clipboardData?.items;
  if (!items) return;

  for (const item of items) {
    if (item.kind === "file" && item.type.startsWith("image/")) {
      e.preventDefault();
      const file = item.getAsFile();
      if (!file) return;

      if (!ALLOWED_IMAGE_TYPES.includes(file.type)) {
        alert("Please paste a PNG, JPEG, GIF, or WebP image.");
        return;
      }

      setAttachment(file);
      return;
    }
  }
});

function clearAttachment() {
  attachedFile = null;
  fileInput.value = "";
  if (attachedURL) {
    URL.revokeObjectURL(attachedURL);
    attachedURL = null;
  }
  attachPreview.classList.add("hidden");
}

function addMessage(role, text, imageURL) {
  const div = document.createElement("div");
  div.className = "msg " + (role === "user" ? "msg-user" : role === "error" ? "msg-error" : "msg-ai");
  if (imageURL) {
    const img = document.createElement("img");
    img.src = imageURL;
    img.alt = "Uploaded screenshot";
    div.appendChild(img);
  }
  if (text) {
    div.appendChild(document.createTextNode(text));
  }
  chatMessages.appendChild(div);
  chatMessages.scrollTop = chatMessages.scrollHeight;
  return div;
}

chatForm.addEventListener("submit", async (event) => {
  event.preventDefault();

  const message = chatText.value.trim();
  if (!message && !attachedFile) return;

  const formData = new FormData();
  formData.append("lesson_id", LESSON_ID);
  formData.append("message", message);
  formData.append("history", JSON.stringify(history));
  if (attachedFile) formData.append("screenshot", attachedFile);

  // Show the user's message (keep the object URL alive for the thumbnail).
  const shownImageURL = attachedURL;
  attachedURL = null; // ownership moves to the message bubble
  addMessage("user", message, shownImageURL);
  history.push({
    role: "user",
    content: (attachedFile ? "[uploaded a screenshot of my Scratch code] " : "") + (message || "What's wrong with my code?"),
  });

  chatText.value = "";
  clearAttachment();
  sendBtn.disabled = true;
  const typing = addMessage("ai", "Looking at your code…");
  typing.classList.add("msg-typing");

  try {
    const res = await fetch("/api/analyze", { method: "POST", body: formData });
    const data = await res.json();
    typing.remove();
    if (!res.ok || data.error) {
      addMessage("error", data.error || "Something went wrong. Please try again.");
    } else {
      addMessage("ai", data.reply);
      history.push({ role: "assistant", content: data.reply });
    }
  } catch {
    typing.remove();
    addMessage("error", "Couldn't reach the server. Is it still running?");
  } finally {
    sendBtn.disabled = false;
    chatText.focus();
  }
});
