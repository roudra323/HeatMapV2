# HeatMap V2 - User Guide for Web3 Marketers

## Quick Start Guide

### How to Search for Wallets

1. **Search by Address**: Use the search bar at the top of the dashboard
   - Enter full or partial wallet address (e.g., `0x1234` or full address)
   - Press "Search" or hit Enter
   - If exact match found, wallet detail modal opens automatically
   - Partial matches will filter the visualization

2. **Clear Search**: Click "Clear" button to reset filters

### How to Export Wallet Lists

#### Export Button Location
- Found in the top-right corner of the scatter plot visualization
- Shows current filtered wallet count

#### Export Formats

**1. CSV Export** - Best for spreadsheet analysis
- Contains all wallet metrics and behavior ratios
- Columns include:
  - `address`: Full Ethereum address
  - `community`: Behavior classification
  - `total_transactions`: Number of transactions
  - `unique_tokens`: Number of different tokens traded
  - `unique_counterparties`: Number of wallets interacted with
  - `stablecoin_ratio`, `meme_ratio`, `defi_ratio`, `wrapped_ratio`, `nft_ratio`

**2. JSON Export** - Best for developers/automation
- Structured data format
- Includes metadata (export timestamp, total count)
- Each wallet includes full metrics and behavior ratios grouped

**3. TXT Export (Addresses Only)** - Best for quick campaigns
- One address per line
- Easy to copy-paste into:
  - Email marketing tools
  - Airdrop tools
  - Wallet whitelists
  - Other marketing platforms

### How to View Wallet Details

**Method 1: Click on Scatter Plot**
- Click any point in the PCA or t-SNE visualization
- Wallet detail modal opens

**Method 2: Search for Exact Address**
- Enter full wallet address in search bar
- Modal opens automatically if found

**Modal Contents:**
- Full wallet address with copy button
- Community classification badge
- Activity metrics (transactions, tokens, counterparties)
- Behavior breakdown with visual percentages
- Embedding coordinates (for advanced users)
- Quick links to Etherscan and DeBank

## Common Workflows

### Workflow 1: Export NFT Traders for Airdrop

1. Click on "NFT Trader" in Community Statistics sidebar (right panel)
2. Visualization updates to show only NFT traders (127 wallets)
3. Click "Export Wallets" button
4. Select "Addresses Only (TXT)"
5. File downloads as `heatmap_nft_trader_2025-11-15_addresses.txt`
6. Copy-paste addresses into your airdrop tool

### Workflow 2: Find High-Value Stablecoin Users

1. Select "Stablecoin User" from community filter
2. Review the 65 wallets in visualization
3. Click individual points to check transaction volume
4. Export as CSV for detailed analysis
5. Sort by `total_transactions` or `unique_counterparties` in spreadsheet

### Workflow 3: Research Specific Wallet

1. Paste wallet address in search bar
2. Click Search
3. Review wallet detail modal:
   - Check community classification
   - Verify transaction count
   - Analyze behavior ratios
4. Click "View on Etherscan" for transaction history
5. Click "View on DeBank" for portfolio analysis

### Workflow 4: Identify Similar Wallets

1. Search or click on a target wallet
2. Note its community type (e.g., "Mixed Behavior")
3. Filter by that community
4. Use t-SNE view to find nearby wallets (similar behavior)
5. Export the cluster for targeted outreach

### Workflow 5: Build Marketing Segments

**Scenario: Launching a new DeFi protocol**

1. Export "DeFi User" community
2. Export "High Activity Hub" community (likely to be influencers)
3. Export "Active Trader" community
4. Combine CSV files in spreadsheet
5. Sort by transaction count to prioritize high-value targets
6. Use addresses for:
   - Email campaigns (if you have matched data)
   - Token airdrops
   - Discord invites
   - Twitter outreach

**Scenario: NFT Project Launch**

1. Filter by "NFT Trader" community
2. Review t-SNE clustering to find sub-groups
3. Export full CSV with metrics
4. Segment by:
   - High transaction count = Active collectors
   - High unique tokens = Diverse tastes
   - High counterparties = Influencers/traders
5. Target each segment with different messaging

## Tips & Best Practices

### Filtering Tips
- Use **community filters** for broad segmentation
- Use **search** for specific wallet research
- Combine filters: Select community THEN search within it

### Export Tips
- **CSV**: Use for analysis in Excel/Google Sheets
- **JSON**: Use for programmatic processing
- **TXT**: Use for quick imports into other tools
- Filenames include date and community for easy organization

### Visualization Tips
- **t-SNE**: Better for finding similar wallets (local clusters)
- **PCA**: Better for overall community separation
- **Network Graph**: Shows actual wallet connections
- Click "Show Network" for relationship mapping

### Privacy & Ethics
- Wallet addresses are public blockchain data
- Use responsibly for:
  - ✅ Product-market fit research
  - ✅ Airdrop targeting
  - ✅ Community building
- Avoid:
  - ❌ Spam
  - ❌ Unsolicited outreach without value
  - ❌ Sharing personal data without consent

## Keyboard Shortcuts

- **Search**: Click search bar or start typing
- **Clear Search**: ESC key (when search is active)
- **Close Modal**: ESC key or click outside

## Troubleshooting

**Q: Search returns no results**
- Verify address format (starts with 0x)
- Try partial address (first 6-10 characters)
- Address may not be in analyzed dataset (511 wallets)

**Q: Export button shows 0 wallets**
- Check your filters - may be too restrictive
- Try selecting "All Communities"
- Clear search if active

**Q: Can't click on scatter plot points**
- Ensure you're clicking directly on a point (circle)
- Try zooming in if points are very small
- Some points may be hidden behind others

**Q: Modal won't close**
- Click X button in top-right
- Click outside the modal
- Press ESC key

## Advanced Features

### Understanding Behavior Ratios
- Values are 0.0 to 1.0 (0% to 100%)
- Sum may not equal 100% (categories can overlap)
- Use to understand primary wallet focus

### Understanding Coordinates
- **PCA**: Linear projection, variance-based
- **t-SNE**: Non-linear, preserves local structure
- Higher values = different end of spectrum
- Nearby points = similar behavior patterns

### Interpreting Communities
- Communities are rule-based (not clustering)
- Multiple behaviors possible (e.g., NFT + DeFi)
- "Mixed Behavior" = no dominant pattern
- "High Activity Hub" = many connections (potential influencer)

## Support

For issues or feature requests:
- Check documentation: `/README.md`
- Review API docs: `http://localhost:8000/docs` (when backend running)
- File issue on GitHub repository

## Data Update

To refresh with latest blockchain data:
```bash
cd backend
python visualize.py  # Re-run analysis
# Refresh frontend to see new data
```

Current dataset: 511 wallets, 21,181 transfers (minimal sample)

For full dataset collection, configure API keys and use collectors.
