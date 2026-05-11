const form = document.querySelector("#chatForm");
const input = document.querySelector("#messageInput");
const messagesEl = document.querySelector("#messages");
const recsEl = document.querySelector("#recommendations");
const resetButton = document.querySelector("#resetButton");

let messages = [];

function addMessage(role, content) {
  messages.push({ role, content });
  renderMessages();
}

function renderMessages() {
  messagesEl.innerHTML = "";
  if (messages.length === 0) {
    const welcome = document.createElement("div");
    welcome.className = "message assistant";
    welcome.textContent = "Tell me the role, seniority, skills, and any duration limit.";
    messagesEl.appendChild(welcome);
    return;
  }

  for (const message of messages) {
    const bubble = document.createElement("div");
    bubble.className = `message ${message.role}`;
    bubble.textContent = message.content;
    messagesEl.appendChild(bubble);
  }
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

function renderRecommendations(recommendations) {
  recsEl.innerHTML = "";
  recsEl.classList.toggle("empty", recommendations.length === 0);

  if (recommendations.length === 0) {
    const empty = document.createElement("p");
    empty.textContent = "No recommendations yet.";
    recsEl.appendChild(empty);
    return;
  }

  for (const rec of recommendations) {
    const item = document.createElement("article");
    item.className = "rec";

    const top = document.createElement("div");
    top.className = "rec-top";

    const title = document.createElement("h3");
    title.textContent = rec.name;

    const type = document.createElement("span");
    type.className = "type";
    type.textContent = rec.test_type || "SHL";

    const link = document.createElement("a");
    link.href = rec.url;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.textContent = "Catalog page";

    top.append(title, type);
    item.append(top, link);
    recsEl.appendChild(item);
  }
}

async function sendMessage(content) {
  addMessage("user", content);
  input.value = "";
  input.disabled = true;

  try {
    const response = await fetch("/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ messages }),
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const data = await response.json();
    addMessage("assistant", data.reply);
    renderRecommendations(data.recommendations || []);
  } catch (error) {
    addMessage("assistant", "I could not reach the API. Please try again.");
    renderRecommendations([]);
  } finally {
    input.disabled = false;
    input.focus();
  }
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  const content = input.value.trim();
  if (content) {
    sendMessage(content);
  }
});

resetButton.addEventListener("click", () => {
  messages = [];
  input.value = "";
  renderMessages();
  renderRecommendations([]);
  input.focus();
});

input.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
    form.requestSubmit();
  }
});

renderMessages();
renderRecommendations([]);
