// dataEntry.js

// Array to store portfolio assets
export let portfolio = [];

/**
 * Adds a new asset to the portfolio and returns updated HTML to display it.
 * @param {string} assetName - The name of the asset.
 * @param {string} assetType - The type of asset.
 * @param {number|string} quantity - The quantity of the asset.
 * @param {number|string} purchasePrice - The purchase price of the asset.
 * @returns {string} HTML string representing the updated portfolio.
 */
export function handleManualForm(assetName, assetType, quantity, purchasePrice) {
  // Create an asset object and convert numerical fields
  const asset = {
    assetName,
    assetType,
    quantity: Number(quantity),
    purchasePrice: Number(purchasePrice)
  };

  // Add the new asset to the portfolio array
  portfolio.push(asset);

  // Return the updated portfolio HTML
  return renderPortfolio();
}

/**
 * Generates HTML to display the portfolio as a table.
 * @returns {string} HTML string of the portfolio table.
 */
function renderPortfolio() {
  if (portfolio.length === 0) {
    return "<p>No assets added yet.</p>";
  }

  // Build HTML table
  let html = "<h3>Your Portfolio</h3>";
  html += "<table>";
  html += "<tr><th>Asset Name</th><th>Asset Type</th><th>Quantity</th><th>Purchase Price</th></tr>";
  
  portfolio.forEach(asset => {
    html += `<tr>
               <td>${asset.assetName}</td>
               <td>${asset.assetType}</td>
               <td>${asset.quantity}</td>
               <td>${asset.purchasePrice}</td>
             </tr>`;
  });
  
  html += "</table>";
  return html;
}

/**
 * Parses a CSV file and adds each row as an asset to the portfolio.
 * (For simplicity, this example assumes a CSV with headers matching the asset properties.)
 * @param {File} file - The CSV file to parse.
 * @returns {Promise<string>} Promise resolving with updated portfolio HTML.
 */
export function parseCSVFile(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = function(e) {
      try {
        const rows = e.target.result.split("\n").filter(row => row.trim() !== "");
        // Assume the first row contains headers: assetName, assetType, quantity, purchasePrice
        const headers = rows[0].split(",");
        for (let i = 1; i < rows.length; i++) {
          const values = rows[i].split(",");
          let asset = {};
          headers.forEach((header, index) => {
            // Convert numerical fields if applicable
            asset[header.trim()] = (header.trim() === "quantity" || header.trim() === "purchasePrice")
              ? Number(values[index])
              : values[index].trim();
          });
          portfolio.push(asset);
        }
        resolve(renderPortfolio());
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
