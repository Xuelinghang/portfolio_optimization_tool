// dataEntry.js

export let portfolioEntries = [];

export function initPortfolioEntries() {
  portfolioEntries = [];
  // Initialize with 5 empty entries
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
    row.style.position = "relative"; // For suggestions positioning

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
    });

    // Search Button
    const searchBtn = document.createElement("button");
    searchBtn.textContent = "Search";
    searchBtn.className = "small-btn";
    searchBtn.style.marginRight = "10px";
    searchBtn.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      searchAlphaVantage(tickerInput, index, row);
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
    deleteBtn.className = "small-btn";
    deleteBtn.style.marginLeft = "10px";
    deleteBtn.addEventListener("click", () => {
      deleteEntry(index);
    });

    // Suggestions container for this row
    const suggestionsContainer = document.createElement("div");
    suggestionsContainer.className = "suggestions-row";
    suggestionsContainer.style.position = "absolute";
    suggestionsContainer.style.top = "40px";
    suggestionsContainer.style.left = "0";
    suggestionsContainer.style.width = tickerInput.offsetWidth + "px";
    suggestionsContainer.style.display = "none";

    row.appendChild(tickerInput);
    row.appendChild(searchBtn);
    row.appendChild(allocationInput);
    row.appendChild(deleteBtn);
    row.appendChild(suggestionsContainer);
    container.appendChild(row);
  });
}

function searchAlphaVantage(tickerInput, index, row) {
  const query = tickerInput.value.trim();
  if (!query) return;

  // Replace with your actual Alpha Vantage API key
  const apiKey = "CSVWIRSNGKIT4MB7";
  const url = `https://www.alphavantage.co/query?function=SYMBOL_SEARCH&keywords=${encodeURIComponent(query)}&apikey=${apiKey}`;

  fetch(url)
    .then((response) => response.json())
    .then((data) => {
      const suggestionsContainer = row.querySelector(".suggestions-row");
      suggestionsContainer.style.width = tickerInput.offsetWidth + "px";
      suggestionsContainer.innerHTML = "";
      if (data.bestMatches && data.bestMatches.length > 0) {
        data.bestMatches.forEach((match) => {
          const symbol = match["1. symbol"];
          const name = match["2. name"];
          const item = document.createElement("div");
          item.className = "suggestion-item";
          item.textContent = `${symbol} - ${name}`;
          item.addEventListener("click", () => {
            portfolioEntries[index].ticker = symbol;
            tickerInput.value = symbol;
            suggestionsContainer.style.display = "none";
          });
          suggestionsContainer.appendChild(item);
        });
        suggestionsContainer.style.display = "block";
      } else {
        suggestionsContainer.style.display = "none";
      }
    })
    .catch((error) => {
      console.error("Error fetching company data:", error);
    });
}

export function addEntry() {
  portfolioEntries.push({ ticker: "", allocation: "" });
  renderPortfolioEntries();
}

export function deleteEntry(i) {
  portfolioEntries.splice(i, 1);
  renderPortfolioEntries();
}

// Modified CSV parsing function
export function parseCSVFile(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = function(e) {
      try {
        const text = e.target.result;
        const rows = parseCSV(text);
        const headers = rows[0].map(h => h.toLowerCase());
        
        // Validate CSV structure
        if (!headers.includes('symbol')) {
          throw new Error('CSV must contain "Symbol" column');
        }
        
        const isPercentage = headers.includes('weight');
        const isDollar = headers.includes('balance');
        
        if (!isPercentage && !isDollar) {
          throw new Error('CSV must contain either "Weight" or "Balance" column');
        }

        // Clear existing entries
        portfolioEntries.length = 0;
        
        // Process rows
        let totalBalance = 0;
        const balances = [];
        
        for (let i = 1; i < rows.length; i++) {
          const row = rows[i];
          const symbol = row[headers.indexOf('symbol')];
          
          if (isPercentage) {
            const weight = parsePercentage(row[headers.indexOf('weight')]);
            portfolioEntries.push({
              ticker: symbol,
              allocation: weight
            });
          } else if (isDollar) {
            const balance = parseDollar(row[headers.indexOf('balance')]);
            balances.push(balance);
            totalBalance += balance;
          }
        }

        // Convert dollar balances to percentages
        if (isDollar) {
          balances.forEach((balance, index) => {
            const allocation = (balance / totalBalance) * 100;
            portfolioEntries.push({
              ticker: rows[index + 1][headers.indexOf('symbol')],
              allocation: Number(allocation.toFixed(2))
            });
          });
        }

        validatePortfolio();
        renderPortfolioEntries();
        resolve(`${rows.length - 1} assets imported successfully`);
      } catch (err) {
        portfolioEntries.length = 0;
        reject(err);
      }
    };
    reader.onerror = reject;
    reader.readAsText(file);
  });
}

function parseCSV(text) {
  return text.split(/\r?\n/)
    .filter(row => row.trim() !== '')
    .map(row => row.split(/,(?=(?:(?:[^"]*"){2})*[^"]*$)/)
      .map(cell => cell.replace(/^"|"$/g, '').trim()));
}

function parsePercentage(value) {
  const cleanValue = value.replace(/%/g, '');
  const num = Number(cleanValue);
  if (isNaN(num)) throw new Error(`Invalid percentage: ${value}`);
  return num;
}

function parseDollar(value) {
  const cleanValue = value.replace(/[$,]/g, '');
  const num = Number(cleanValue);
  if (isNaN(num)) throw new Error(`Invalid dollar amount: ${value}`);
  return num;
}

function validatePortfolio() {
  // Check allocation sum
  const totalAllocation = portfolioEntries.reduce((sum, entry) => 
    sum + entry.allocation, 0);
  
  if (Math.abs(totalAllocation - 100) > 1) {
    throw new Error(`Total allocation ${totalAllocation.toFixed(2)}% (must be 100%)`);
  }

  // Check duplicate symbols
  const symbols = new Set();
  portfolioEntries.forEach(entry => {
    if (symbols.has(entry.ticker)) {
      throw new Error(`Duplicate symbol: ${entry.ticker}`);
    }
    symbols.add(entry.ticker);
  });
}

// Hide suggestions when clicking outside
document.addEventListener("click", function(e) {
  const suggestionBoxes = document.querySelectorAll(".suggestions-row");
  suggestionBoxes.forEach((box) => {
    if (!box.contains(e.target)) {
      box.style.display = "none";
    }
  });
});

// Optionally expose functions globally if needed
window.renderPortfolioEntries = renderPortfolioEntries;
window.initPortfolioEntries = initPortfolioEntries;
window.portfolioEntries = portfolioEntries;
window.addEntry = addEntry;
window.parseCSVFile = parseCSVFile;
window.deleteEntry = deleteEntry;
