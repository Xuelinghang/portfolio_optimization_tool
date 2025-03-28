export let portfolioEntries = [];

export function initPortfolioEntries() {
  portfolioEntries = [];
  for (let i = 0; i < 5; i++) {
    portfolioEntries.push({ ticker: "", allocation: "" });
  }
  renderPortfolioEntries();
}

export function renderPortfolioEntries() {
  const container = document.getElementById("portfolioEntries");
  if (!container) return;
  container.innerHTML = "";

  portfolioEntries.forEach((entry, index) => {
    const row = document.createElement("div");
    row.style.display = "flex";
    row.style.alignItems = "center";
    row.style.marginBottom = "10px";
    row.style.position = "relative";

    // Ticker/Company Input
    const tickerInput = document.createElement("input");
    tickerInput.type = "text";
    tickerInput.placeholder = "Ticker or Company";
    tickerInput.value = entry.ticker;
    tickerInput.style.padding = "8px";
    tickerInput.style.border = "1px solid #ccc";
    tickerInput.style.borderRadius = "4px";
    tickerInput.style.marginRight = "10px";
    tickerInput.style.flex = "1";
    tickerInput.addEventListener("input", (e) => {
      portfolioEntries[index].ticker = e.target.value;
      // Automatically refresh the suggestion list on every character change.
      searchCompanies(tickerInput, index, row);
    });

    // Search Button
    const searchBtn = document.createElement("button");
    searchBtn.textContent = "Search";
    searchBtn.style.padding = "5px 8px";
    searchBtn.style.marginRight = "10px";
    searchBtn.style.border = "1px solid #ccc";
    searchBtn.style.borderRadius = "4px";
    searchBtn.style.cursor = "pointer";
    searchBtn.style.backgroundColor = "#d3e5d1";
    searchBtn.style.fontWeight = "bold";
    searchBtn.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation(); // Prevent event from bubbling to the document-level handler.
      searchCompanies(tickerInput, index, row);
    });

    // Allocation Input
    const allocationInput = document.createElement("input");
    allocationInput.type = "number";
    allocationInput.placeholder = "Allocation %";
    allocationInput.value = entry.allocation;
    allocationInput.style.padding = "8px";
    allocationInput.style.border = "1px solid #ccc";
    allocationInput.style.borderRadius = "4px";
    allocationInput.style.flex = "0.5";
    allocationInput.style.marginLeft = "10px";
    allocationInput.addEventListener("input", (e) => {
      portfolioEntries[index].allocation = e.target.value;
    });

    // Delete Button
    const deleteBtn = document.createElement("button");
    deleteBtn.textContent = "Delete";
    deleteBtn.style.padding = "5px 8px";
    deleteBtn.style.marginLeft = "10px";
    deleteBtn.style.border = "1px solid #ccc";
    deleteBtn.style.borderRadius = "4px";
    deleteBtn.style.cursor = "pointer";
    deleteBtn.style.backgroundColor = "#d3e5d1";
    deleteBtn.style.fontWeight = "bold";
    deleteBtn.addEventListener("click", () => {
      deleteEntry(index);
    });

    row.appendChild(tickerInput);
    row.appendChild(searchBtn);
    row.appendChild(allocationInput);
    row.appendChild(deleteBtn);
    container.appendChild(row);
  });
}

function searchCompanies(tickerInput, index, row) {
  const query = tickerInput.value.trim();

  // Remove any previous suggestion box in this row
  const oldSuggestion = row.querySelector(".suggestions");
  if (oldSuggestion) {
    oldSuggestion.remove();
  }

  if (!query) return;

  const apiUrl = `https://www.alphavantage.co/query?function=SYMBOL_SEARCH&keywords=${encodeURIComponent(query)}&apikey=EC5NXFAP19U52ZVD`;

  fetch(apiUrl)
    .then(response => response.json())
    .then(data => {
      const matches = data.bestMatches || [];
      if (!matches.length) return;

      const suggestionDiv = document.createElement("div");
      suggestionDiv.className = "suggestions";
      suggestionDiv.style.position = "absolute";
      suggestionDiv.style.background = "white";
      suggestionDiv.style.border = "1px solid #ccc";
      suggestionDiv.style.top = "100%";
      suggestionDiv.style.left = "0";
      suggestionDiv.style.zIndex = "20";
      // Set suggestion width equal to the ticker input's width.
      suggestionDiv.style.width = tickerInput.offsetWidth + "px";
      suggestionDiv.style.maxHeight = "150px";
      suggestionDiv.style.overflowY = "auto";
      suggestionDiv.style.boxShadow = "0 4px 8px rgba(0,0,0,0.1)";
      suggestionDiv.style.marginTop = "5px";

      // Ensure suggestions stack vertically.
      suggestionDiv.style.display = "flex";
      suggestionDiv.style.flexDirection = "column";
      suggestionDiv.style.alignItems = "flex-start";

      matches.forEach(result => {
        const symbol = result["1. symbol"];
        const name = result["2. name"];
        const item = document.createElement("div");
        item.textContent = `${symbol} - ${name}`;
        item.style.display = "block";
        item.style.padding = "6px";
        item.style.cursor = "pointer";
        item.addEventListener("mouseover", () => {
          item.style.backgroundColor = "#f1f1f1";
        });
        item.addEventListener("mouseout", () => {
          item.style.backgroundColor = "white";
        });
        item.addEventListener("click", () => {
          portfolioEntries[index].ticker = symbol;
          tickerInput.value = symbol;
          suggestionDiv.remove();
        });
        suggestionDiv.appendChild(item);
      });

      row.appendChild(suggestionDiv);
    })
    .catch(err => {
      console.error("Error fetching company data:", err);
    });
}

export function addEntry() {
  portfolioEntries.push({ ticker: "", allocation: "" });
  renderPortfolioEntries();
}

export function deleteEntry(index) {
  portfolioEntries.splice(index, 1);
  renderPortfolioEntries();
}

export function parseCSVFile(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = function(e) {
      try {
        const rows = e.target.result.split("\n").filter(row => row.trim() !== "");
        const headers = rows[0].split(",");
        for (let i = 1; i < rows.length; i++) {
          const values = rows[i].split(",");
          let asset = {};
          headers.forEach((header, idx) => {
            asset[header.trim()] = (header.trim() === "quantity" || header.trim() === "purchasePrice")
              ? Number(values[idx])
              : values[idx].trim();
          });
          portfolioEntries.push(asset);
        }
        renderPortfolioEntries();
        resolve("CSV Parsed and entries added.");
      } catch (err) {
        reject(err);
      }
    };
    reader.onerror = function(err) {
      reject(err);
    };
    reader.readAsText(file);
  });
}

// Single document-level click handler to remove any open suggestion lists
document.addEventListener("click", function(e) {
  const suggestions = document.querySelectorAll(".suggestions");
  suggestions.forEach(suggestion => {
    const parentRow = suggestion.parentNode;
    const input = parentRow.querySelector("input[type='text']");
    if (input && !input.contains(e.target) && !suggestion.contains(e.target)) {
      suggestion.remove();
    }
  });
});
