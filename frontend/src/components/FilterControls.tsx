interface FilterControlsProps {
  communities: string[]
  selectedCommunity: string
  onCommunityChange: (community: string) => void
  visualizationMethod: 'pca' | 'tsne'
  onMethodChange: (method: 'pca' | 'tsne') => void
  showNetwork: boolean
  onShowNetworkChange: (show: boolean) => void
}

export default function FilterControls({
  communities,
  selectedCommunity,
  onCommunityChange,
  visualizationMethod,
  onMethodChange,
  showNetwork,
  onShowNetworkChange,
}: FilterControlsProps) {
  return (
    <div className="bg-slate-800/50 rounded-lg border border-purple-500/20 p-6">
      <h2 className="text-xl font-bold mb-4">Filters & Controls</h2>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {/* Community Filter */}
        <div>
          <label className="block text-sm font-medium text-purple-300 mb-2">
            Behavior Community
          </label>
          <select
            value={selectedCommunity}
            onChange={(e) => onCommunityChange(e.target.value)}
            className="w-full bg-slate-700 border border-purple-500/30 rounded-lg px-4 py-2 text-white focus:outline-none focus:ring-2 focus:ring-purple-500"
          >
            <option value="all">All Communities</option>
            {communities.map((community) => (
              <option key={community} value={community}>
                {community}
              </option>
            ))}
          </select>
        </div>

        {/* Visualization Method */}
        <div>
          <label className="block text-sm font-medium text-purple-300 mb-2">
            Visualization Method
          </label>
          <div className="flex gap-2">
            <button
              onClick={() => onMethodChange('pca')}
              className={`flex-1 px-4 py-2 rounded-lg font-medium transition-all ${
                visualizationMethod === 'pca'
                  ? 'bg-purple-600 text-white'
                  : 'bg-slate-700 text-gray-400 hover:bg-slate-600'
              }`}
            >
              PCA
            </button>
            <button
              onClick={() => onMethodChange('tsne')}
              className={`flex-1 px-4 py-2 rounded-lg font-medium transition-all ${
                visualizationMethod === 'tsne'
                  ? 'bg-purple-600 text-white'
                  : 'bg-slate-700 text-gray-400 hover:bg-slate-600'
              }`}
            >
              t-SNE
            </button>
          </div>
        </div>

        {/* Network Toggle */}
        <div>
          <label className="block text-sm font-medium text-purple-300 mb-2">
            Network Graph
          </label>
          <button
            onClick={() => onShowNetworkChange(!showNetwork)}
            className={`w-full px-4 py-2 rounded-lg font-medium transition-all ${
              showNetwork
                ? 'bg-green-600 text-white'
                : 'bg-slate-700 text-gray-400 hover:bg-slate-600'
            }`}
          >
            {showNetwork ? 'Hide Network' : 'Show Network'}
          </button>
        </div>
      </div>
    </div>
  )
}
