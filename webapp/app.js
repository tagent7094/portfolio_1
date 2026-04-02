const API = '';

// =========================================================================
// State
// =========================================================================
let graphData = { nodes: [], edges: [] };
let graphFilter = 'all';
let selectedNode = null;
let lastGenResult = null;

// vis-network objects
let visNetwork = null;
let visNodes = null;
let visEdges = null;

// Expandable graph state
let expandedNodes = new Set();       // set of node IDs currently expanded
let allNodesById = {};               // id -> node data
let allEdges = [];                   // raw edge list from API
let childrenOf = {};                 // parentId -> [childNodeIds]

// =========================================================================
// Color palette
// =========================================================================
const NODE_COLORS = {
    founder:        { bg: '#ffffff', border: '#c4c7d4', font: '#0a0c12' },
    category:       { bg: '#3b3f54', border: '#5e6380', font: '#e4e6f0' },
    belief:         { bg: '#6c63ff', border: '#8b84ff', font: '#e4e6f0' },
    story:          { bg: '#60a5fa', border: '#93c5fd', font: '#e4e6f0' },
    style_rule:     { bg: '#fbbf24', border: '#fcd34d', font: '#1a1d27' },
    thinking_model: { bg: '#34d399', border: '#6ee7b7', font: '#1a1d27' },
    vocabulary:     { bg: '#f87171', border: '#fca5a5', font: '#e4e6f0' },
    contrast_pair:  { bg: '#f472b6', border: '#f9a8d4', font: '#e4e6f0' },
    unknown:        { bg: '#888780', border: '#a8a29e', font: '#e4e6f0' },
};

const NODE_SIZES = {
    founder: 40,
    category: 28,
    belief: 14,
    story: 14,
    style_rule: 10,
    thinking_model: 12,
    vocabulary: 12,
    contrast_pair: 10,
};

// Fixed positions for the initial hub layout (founder center, categories around)
const HUB_POSITIONS = {
    founder:        { x: 0,    y: 0 },
    cat_beliefs:    { x: -300, y: -200 },
    cat_stories:    { x: 300,  y: -200 },
    cat_style:      { x: -350, y: 200 },
    cat_models:     { x: 350,  y: 200 },
    cat_vocabulary: { x: 0,    y: 350 },
};

// =========================================================================
// Navigation
// =========================================================================
function showSection(id, btn) {
    document.querySelectorAll('.section').forEach(s => s.classList.remove('active'));
    document.querySelectorAll('header nav button').forEach(b => b.classList.remove('active'));
    document.getElementById(id).classList.add('active');
    if (btn) btn.classList.add('active');
    if (id === 'dashboard') { loadStats(); loadPersonalityCard(); }
    if (id === 'graph') loadGraph();
    if (id === 'coverage') loadCoverage();
    if (id === 'history') loadHistory();
    if (id === 'config') loadConfig();
}

// =========================================================================
// Dashboard
// =========================================================================
async function loadStats() {
    try {
        const res = await fetch(`${API}/api/graph/stats`);
        const data = await res.json();
        document.getElementById('stat-nodes').textContent = data.nodes || 0;
        document.getElementById('stat-edges').textContent = data.edges || 0;
        document.getElementById('stat-beliefs').textContent = data.types?.belief || 0;
        document.getElementById('stat-stories').textContent = data.types?.story || 0;
        document.getElementById('stat-styles').textContent = data.types?.style_rule || 0;
        document.getElementById('stat-models').textContent = data.types?.thinking_model || 0;
    } catch (e) { console.error('Failed to load stats:', e); }
}

async function loadPersonalityCard() {
    try {
        const res = await fetch(`${API}/api/graph/personality-card`);
        const data = await res.json();
        const el = document.getElementById('personality-card');
        el.textContent = data.card ? data.card.substring(0, 800) + (data.card.length > 800 ? '...' : '') : 'No personality card yet. Run ingestion first.';
    } catch (e) { document.getElementById('personality-card').textContent = 'Failed to load.'; }
}

async function runIngest() {
    const btn = document.getElementById('btn-ingest');
    const status = document.getElementById('ingest-status');
    btn.disabled = true;
    status.innerHTML = '<span class="status loading"><span class="spinner"></span> Running ingestion...</span>';
    try {
        const res = await fetch(`${API}/api/ingest`, { method: 'POST' });
        const data = await res.json();
        if (data.status === 'ok') {
            status.innerHTML = '<span class="status ok">Ingestion complete</span>';
            loadStats(); loadPersonalityCard();
        } else {
            status.innerHTML = `<span class="status error">Error: ${esc(data.stderr || 'Unknown')}</span>`;
        }
    } catch (e) { status.innerHTML = `<span class="status error">Failed: ${esc(e.message)}</span>`; }
    finally { btn.disabled = false; }
}

// =========================================================================
// Generate — Pipeline with SSE streaming
// =========================================================================

// Pipeline state
let pipelinePosts = [];      // all 10 generated posts
let pipelineVotes = {};      // {agent_id: {post_id: {score, feedback}}}
let pipelineAgentNames = {}; // {agent_id: agent_name}

function resetPipelineUI() {
    pipelinePosts = [];
    pipelineVotes = {};
    pipelineAgentNames = {};
    document.getElementById('pipeline-viz').style.display = 'flex';
    document.getElementById('stage-panels').style.display = 'block';

    // Reset all steps
    document.querySelectorAll('.step').forEach(s => { s.className = 'step pending'; });

    // Reset panels
    ['panel-generate', 'panel-vote', 'panel-refine', 'panel-massacre', 'panel-final'].forEach(id => {
        document.getElementById(id).style.display = 'none';
    });
    document.getElementById('posts-grid').innerHTML = '';
    document.getElementById('voting-matrix').innerHTML = '';
    document.getElementById('vote-summary').innerHTML = '';
    document.getElementById('refinement-panels').innerHTML = '';
    document.getElementById('final-post').value = '';
    document.getElementById('final-quality').innerHTML = '';
    document.getElementById('final-scores').innerHTML = '';
    document.getElementById('gen-count').textContent = '0/10';
}

function setStepState(stage, state) {
    const stepMap = { match_topic: 'generate', generate_all_posts: 'generate', audience_vote: 'vote', select_top: 'vote', refine_posts: 'refine', select_final: 'refine', opening_massacre: 'massacre', humanize: 'humanize', quality_gate: 'humanize', track_coverage: 'humanize' };
    const stepId = stepMap[stage] || stage;
    const el = document.getElementById(`step-${stepId}`);
    if (!el) return;
    el.className = `step ${state}`;
    if (state === 'completed') {
        el.querySelector('.step-indicator').textContent = '✓';
    }
}

async function generateTopic() {
    const topic = document.getElementById('topic-input').value.trim();
    if (!topic) return alert('Enter a topic');
    const platform = document.getElementById('topic-platform').value;
    const btn = document.getElementById('btn-gen-topic');
    const status = document.getElementById('topic-status');
    btn.disabled = true;
    status.innerHTML = '<span class="status loading"><span class="spinner"></span> Starting pipeline (10 engines + 5 audience agents)...</span>';

    resetPipelineUI();

    try {
        const res = await fetch(`${API}/api/generate/topic/stream`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ topic, platform, creativity: (document.getElementById('creativity-slider')?.value || 50) / 100 }),
        });

        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n\n');
            buffer = lines.pop() || '';

            for (const line of lines) {
                const trimmed = line.trim();
                if (!trimmed || !trimmed.startsWith('data: ')) continue;
                try {
                    const event = JSON.parse(trimmed.substring(6));
                    handlePipelineEvent(event, topic);
                } catch (e) { /* skip parse errors */ }
            }
        }

        status.innerHTML = '<span class="status ok">Pipeline complete</span>';
    } catch (e) {
        status.innerHTML = `<span class="status error">Failed: ${esc(e.message)}</span>`;
    } finally {
        btn.disabled = false;
    }
}

function handlePipelineEvent(event, topic) {
    const { stage, status, data, progress, agent_id } = event;

    switch (stage) {
        case 'match_topic':
            setStepState('match_topic', status === 'completed' ? 'active' : 'active');
            break;

        case 'generate_all_posts':
            setStepState('generate_all_posts', 'active');
            document.getElementById('panel-generate').style.display = 'block';
            if (status === 'generating') {
                // Create a live-streaming card placeholder
                createStreamingCard(data.engine_id, data.engine_name, data.post_index);
            }
            if (status === 'progress' && data.post) {
                // Engine finished — finalize the card with full post
                finalizeStreamingCard(data.post, data.engine_name, data.post_index);
            }
            if (status === 'completed') {
                setStepState('generate_all_posts', 'completed');
            }
            break;

        case 'llm_token':
            // Live streaming tokens into the active card
            if (data.token) {
                appendTokenToCard(data.engine_id, data.token);
            }
            break;

        case 'audience_vote':
            setStepState('audience_vote', 'active');
            document.getElementById('panel-vote').style.display = 'block';
            if (status === 'progress' && data.votes) {
                pipelineVotes[data.agent_id] = data.votes;
                pipelineAgentNames[data.agent_id] = data.agent_name;
                renderVotingMatrix();
            }
            if (status === 'completed') {
                setStepState('audience_vote', 'completed');
                if (data.top_ids) {
                    renderVoteSummary(data.top_ids, data.aggregated);
                }
            }
            break;

        case 'select_top':
            break;

        case 'refine_posts':
            setStepState('refine_posts', 'active');
            document.getElementById('panel-refine').style.display = 'block';
            if (status === 'progress') {
                addRefinementPanel(data);
            }
            if (status === 'completed') {
                setStepState('refine_posts', 'completed');
            }
            break;

        case 'select_final':
            break;

        case 'opening_massacre':
            setStepState('opening_massacre', 'active');
            document.getElementById('panel-massacre').style.display = 'block';
            if (status === 'generating' && data.openings) {
                renderOpeningLines(data.openings);
            }
            if (status === 'voting' && data.votes) {
                renderOpeningVotes(data.agent_name, data.votes);
            }
            if (status === 'completed') {
                setStepState('opening_massacre', 'completed');
                if (data.winning_text) {
                    renderOpeningWinner(data.winning_text, data.aggregated);
                }
            }
            break;

        case 'humanize':
            setStepState('humanize', 'active');
            break;

        case 'quality_gate':
            if (status === 'completed') {
                setStepState('quality_gate', 'completed');
            }
            break;

        case 'track_coverage':
            break;

        case 'done':
        case 'error':
            if (data.error) {
                document.getElementById('topic-status').innerHTML = `<span class="status error">${esc(data.error)}</span>`;
                return;
            }
            showFinalResult(data, topic);
            break;
    }
}

// ── Stage 1: Post Cards (with live streaming) ──

function createStreamingCard(engineId, engineName, index) {
    // Create a card with a live-streaming text area for an engine that's generating.
    const grid = document.getElementById('posts-grid');
    const count = grid.children.length + 1;
    document.getElementById('gen-count').textContent = `${count - 1}/10`;

    const card = document.createElement('div');
    card.className = 'post-card slideIn streaming';
    card.dataset.engineId = engineId;
    card.dataset.postId = `${engineId}_pending`;
    card.innerHTML = `
        <div class="post-card-header">
            <span class="engine-badge">${esc(engineName)}</span>
            <span class="streaming-indicator"><span class="stream-dot"></span> Generating...</span>
        </div>
        <div class="post-card-stream" data-engine="${esc(engineId)}"></div>
    `;
    grid.appendChild(card);
}

function appendTokenToCard(engineId, token) {
    // Append a streamed token to the live card.
    const streamEl = document.querySelector(`.post-card-stream[data-engine="${engineId}"]`);
    if (streamEl) {
        streamEl.textContent += token;
        // Auto-scroll to bottom
        streamEl.scrollTop = streamEl.scrollHeight;
    }
}

function finalizeStreamingCard(post, engineName, index) {
    // Replace the streaming card with the final post card.
    const card = document.querySelector(`.post-card[data-engine-id="${post.engine_id}"]`);
    if (card) {
        card.classList.remove('streaming');
        card.dataset.postId = post.id;
        card.innerHTML = `
            <div class="post-card-header">
                <span class="engine-badge">${esc(engineName || post.engine_name)}</span>
                <span class="post-length">${(post.text || '').length} chars</span>
            </div>
            <div class="post-card-body collapsed">${esc((post.text || '').substring(0, 150))}...</div>
            <button class="btn-expand" onclick="togglePostCard(this)">Show full post</button>
            <div class="post-card-full" style="display:none;">${esc(post.text)}</div>
        `;
    } else {
        // Fallback: add a new card if streaming card not found
        addPostCard(post, engineName, index);
        return;
    }

    const count = document.querySelectorAll('.post-card:not(.streaming)').length;
    document.getElementById('gen-count').textContent = `${count}/10`;
    pipelinePosts.push(post);
}

function addPostCard(post, engineName, index) {
    const grid = document.getElementById('posts-grid');

    const card = document.createElement('div');
    card.className = 'post-card slideIn';
    card.dataset.postId = post.id;
    const preview = (post.text || '').substring(0, 150);
    card.innerHTML = `
        <div class="post-card-header">
            <span class="engine-badge">${esc(engineName || post.engine_name)}</span>
            <span class="post-length">${(post.text || '').length} chars</span>
        </div>
        <div class="post-card-body collapsed">${esc(preview)}...</div>
        <button class="btn-expand" onclick="togglePostCard(this)">Show full post</button>
        <div class="post-card-full" style="display:none;">${esc(post.text)}</div>
    `;
    grid.appendChild(card);

    const count = document.querySelectorAll('.post-card:not(.streaming)').length;
    document.getElementById('gen-count').textContent = `${count}/10`;
    pipelinePosts.push(post);
}

function togglePostCard(btn) {
    const card = btn.parentElement;
    const body = card.querySelector('.post-card-body');
    const full = card.querySelector('.post-card-full');
    if (full.style.display === 'none') {
        full.style.display = 'block';
        body.style.display = 'none';
        btn.textContent = 'Collapse';
    } else {
        full.style.display = 'none';
        body.style.display = 'block';
        btn.textContent = 'Show full post';
    }
}

// ── Stage 2: Voting Matrix ──

function renderVotingMatrix() {
    const matrix = document.getElementById('voting-matrix');
    if (pipelinePosts.length === 0) return;

    let html = '<div class="vote-grid">';
    // Header row
    html += '<div class="vote-header-cell">Agent</div>';
    pipelinePosts.forEach((p, i) => {
        const engineShort = (p.engine_name || p.engine_id || '').split('+')[0].trim().substring(0, 15);
        html += `<div class="vote-header-cell" title="${esc(p.engine_name)}">${esc(engineShort)}</div>`;
    });

    // Agent rows
    for (const [agentId, votes] of Object.entries(pipelineVotes)) {
        const name = pipelineAgentNames[agentId] || agentId;
        html += `<div class="vote-agent-cell">${esc(name)}</div>`;
        pipelinePosts.forEach(p => {
            const v = votes[p.id];
            const score = v ? v.score : '-';
            const feedback = v ? v.feedback : '';
            const color = v ? scoreColor(v.score) : '#333';
            html += `<div class="vote-cell" style="background:${color}" title="${esc(feedback)}">${score}</div>`;
        });
    }

    html += '</div>';
    matrix.innerHTML = html;
}

function scoreColor(score) {
    if (score >= 8) return 'rgba(52, 211, 153, 0.4)';
    if (score >= 6) return 'rgba(251, 191, 36, 0.3)';
    if (score >= 4) return 'rgba(251, 146, 60, 0.25)';
    return 'rgba(248, 113, 113, 0.3)';
}

function renderVoteSummary(topIds, aggregated) {
    const summary = document.getElementById('vote-summary');
    const badges = ['🥇', '🥈', '🥉'];
    let html = '<div class="top-posts-summary"><h3>Top Posts Selected</h3>';
    topIds.forEach((id, i) => {
        const post = pipelinePosts.find(p => p.id === id);
        const agg = aggregated ? aggregated[id] : null;
        const score = agg ? agg.mean : '?';
        html += `<div class="top-post-item">
            <span class="top-badge">${badges[i] || ''}</span>
            <span class="engine-badge">${esc(post?.engine_name || id)}</span>
            <span class="top-score">Avg: ${score}/10</span>
        </div>`;
    });
    html += '</div>';
    summary.innerHTML = html;

    // Highlight winning cards
    document.querySelectorAll('.post-card').forEach(card => {
        if (topIds.includes(card.dataset.postId)) {
            card.classList.add('top-pick');
        }
    });
}

// ── Stage 3: Refinement Panels ──

function addRefinementPanel(data) {
    const container = document.getElementById('refinement-panels');
    const panel = document.createElement('div');
    panel.className = 'comparison-view slideIn';
    panel.innerHTML = `
        <div class="comparison-header">
            <span class="engine-badge">${esc(data.engine_name || data.post_id)}</span>
        </div>
        <div class="comparison-columns">
            <div class="comparison-col original">
                <h4>Original</h4>
                <div class="comparison-text">${esc(data.original_text)}...</div>
            </div>
            <div class="comparison-arrow">→</div>
            <div class="comparison-col refined">
                <h4>Refined</h4>
                <div class="comparison-text">${esc(data.refined_text)}...</div>
            </div>
        </div>
    `;
    container.appendChild(panel);
}

// ── Stage 4: Opening Line Massacre ──

function renderOpeningLines(openings) {
    const grid = document.getElementById('opening-lines-grid');
    grid.innerHTML = openings.map((o, i) => `
        <div class="opening-card slideIn" data-opening-id="${esc(o.id)}">
            <div class="opening-num">#${i + 1}</div>
            <div class="opening-text">${esc(o.text)}</div>
            <div class="opening-strategy">${esc(o.strategy || '')}</div>
        </div>
    `).join('');
}

function renderOpeningVotes(agentName, votes) {
    const container = document.getElementById('opening-votes');
    const row = document.createElement('div');
    row.className = 'opening-vote-row slideIn';
    const cells = Object.entries(votes).map(([lid, v]) =>
        `<span class="vote-cell-mini" style="background:${scoreColor(v.score)}" title="${esc(v.feedback)}">${v.score}</span>`
    ).join('');
    row.innerHTML = `<span class="vote-agent-name">${esc(agentName)}</span>${cells}`;
    container.appendChild(row);
}

function renderOpeningWinner(winningText, aggregated) {
    const el = document.getElementById('opening-winner');
    el.innerHTML = `
        <div class="opening-winner-card">
            <div class="winner-badge">WINNING OPENING</div>
            <div class="winner-text">${esc(winningText)}</div>
        </div>
    `;
    // Highlight winning card
    document.querySelectorAll('.opening-card').forEach(card => {
        card.classList.remove('winner');
    });
}

// ── Stage 5: Final Result ──

function showFinalResult(data, topic) {
    document.getElementById('panel-final').style.display = 'block';
    lastGenResult = data;

    const post = data.humanized_post || '';
    document.getElementById('final-post').value = post;

    const qual = data.quality_result || {};
    document.getElementById('final-quality').innerHTML = `
        <span class="quality-pill ${qual.passed ? 'pass' : 'fail'}">
            ${qual.passed ? 'PASSED' : 'FAILED'} ${qual.score || 0}%
        </span>
    `;

    const inf = data.influence || {};
    document.getElementById('final-scores').innerHTML = `
        <div class="score-item">
            <div class="score-label">Overall</div>
            <div class="score-value">${Math.round(inf.overall || 0)}/100</div>
        </div>
        <div class="score-item">
            <div class="score-label">Belief</div>
            <div class="score-value">${Math.round(inf.belief_alignment?.score || 0)}</div>
        </div>
        <div class="score-item">
            <div class="score-label">Story</div>
            <div class="score-value">${Math.round(inf.story_influence?.score || 0)}</div>
        </div>
        <div class="score-item">
            <div class="score-label">Style</div>
            <div class="score-value">${Math.round(inf.style_adherence?.score || 0)}</div>
        </div>
    `;

    // Store for re-score / copy
    lastGenResult._topic = topic;
}

function copyPost() {
    const post = document.getElementById('final-post').value;
    navigator.clipboard.writeText(post).then(() => showToast('Post copied!'));
}

async function rescorePost() {
    const post = document.getElementById('final-post').value;
    const topic = lastGenResult?._topic || document.getElementById('topic-input').value;
    const platform = document.getElementById('topic-platform').value;
    try {
        const res = await fetch(`${API}/api/score`, {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ post, topic, platform }),
        });
        const data = await res.json();
        if (data.status === 'ok') {
            const inf = data.influence || {};
            const qual = data.quality || {};
            document.getElementById('final-quality').innerHTML = `
                <span class="quality-pill ${qual.passed ? 'pass' : 'fail'}">
                    ${qual.passed ? 'PASSED' : 'FAILED'} ${qual.score || 0}%
                </span>`;
            document.getElementById('final-scores').innerHTML = `
                <div class="score-item"><div class="score-label">Overall</div><div class="score-value">${Math.round(inf.overall || 0)}/100</div></div>
                <div class="score-item"><div class="score-label">Belief</div><div class="score-value">${Math.round(inf.belief_alignment?.score || 0)}</div></div>
                <div class="score-item"><div class="score-label">Story</div><div class="score-value">${Math.round(inf.story_influence?.score || 0)}</div></div>
                <div class="score-item"><div class="score-label">Style</div><div class="score-value">${Math.round(inf.style_adherence?.score || 0)}</div></div>`;
            showToast('Re-scored');
        }
    } catch (e) { showToast('Re-score failed', 'error'); }
}

// =========================================================================
// Generate — Podcast (simple, no SSE)
// =========================================================================
async function generatePodcast() {
    const transcript = document.getElementById('podcast-input').value.trim();
    if (!transcript) return alert('Paste a transcript');
    const platform = document.getElementById('podcast-platform').value;
    const btn = document.getElementById('btn-gen-podcast');
    const status = document.getElementById('podcast-status');
    const output = document.getElementById('podcast-output');
    btn.disabled = true;
    status.innerHTML = '<span class="status loading"><span class="spinner"></span> Generating...</span>';
    output.style.display = 'none';
    try {
        const res = await fetch(`${API}/api/generate/podcast`, {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ transcript, platform }),
        });
        const data = await res.json();
        if (data.post) {
            status.innerHTML = '<span class="status ok">Post generated</span>';
            output.textContent = data.post;
            output.style.display = 'block';
        } else {
            status.innerHTML = `<span class="status error">Error: ${esc(data.stderr || data.detail || 'Unknown')}</span>`;
        }
    } catch (e) { status.innerHTML = `<span class="status error">Failed: ${esc(e.message)}</span>`; }
    finally { btn.disabled = false; }
}

// =========================================================================
// Graph — Core
// =========================================================================
async function loadGraph() {
    try {
        const res = await fetch(`${API}/api/graph/nodes`);
        graphData = await res.json();

        // Index nodes
        allNodesById = {};
        (graphData.nodes || []).forEach(n => { allNodesById[n.id] = n; });
        allEdges = graphData.edges || [];

        // Build children map from CONTAINS edges
        childrenOf = {};
        allEdges.forEach(e => {
            if (e.type === 'CONTAINS' || e.type === 'HAS_CATEGORY') {
                if (!childrenOf[e.source]) childrenOf[e.source] = [];
                childrenOf[e.source].push(e.target);
            }
        });

        // Start with founder expanded (show categories)
        expandedNodes = new Set(['founder']);
        buildVisGraph();
        renderNodeList();
    } catch (e) { console.error('Failed to load graph:', e); }
}

function getVisibleNodes() {
    /** Return the set of node IDs that should be visible based on expansion state. */
    const visible = new Set();

    // Always show founder
    if (allNodesById['founder']) visible.add('founder');

    // If founder is expanded, show categories
    if (expandedNodes.has('founder')) {
        (childrenOf['founder'] || []).forEach(id => visible.add(id));
    }

    // For each expanded category, show its children
    for (const catId of ['cat_beliefs', 'cat_stories', 'cat_style', 'cat_models', 'cat_vocabulary']) {
        if (expandedNodes.has(catId)) {
            (childrenOf[catId] || []).forEach(id => visible.add(id));
        }
    }

    // For each expanded leaf node, show its cross-type connections
    expandedNodes.forEach(nodeId => {
        if (!nodeId.startsWith('cat_') && nodeId !== 'founder') {
            // Show nodes connected via cross-type edges
            allEdges.forEach(e => {
                if (e.type !== 'CONTAINS' && e.type !== 'HAS_CATEGORY') {
                    if (e.source === nodeId && allNodesById[e.target]) visible.add(e.target);
                    if (e.target === nodeId && allNodesById[e.source]) visible.add(e.source);
                }
            });
        }
    });

    return visible;
}

function getVisibleEdges(visibleIds) {
    /** Return edges where both endpoints are visible. */
    return allEdges.filter(e => visibleIds.has(e.source) && visibleIds.has(e.target));
}

function buildVisGraph() {
    const visibleIds = getVisibleNodes();

    // Apply filter
    let filteredIds = visibleIds;
    if (graphFilter !== 'all') {
        filteredIds = new Set();
        // Always keep founder + categories + filtered type
        visibleIds.forEach(id => {
            const n = allNodesById[id];
            if (!n) return;
            if (n.type === 'founder' || n.type === 'category' || n.type === graphFilter) {
                filteredIds.add(id);
            }
        });
    }

    const visibleEdges = getVisibleEdges(filteredIds);

    // Build vis.js node array
    const nodesArr = [];
    filteredIds.forEach(id => {
        const n = allNodesById[id];
        if (!n) return;
        const colors = NODE_COLORS[n.type] || NODE_COLORS.unknown;
        const size = NODE_SIZES[n.type] || 12;
        const isHub = id === 'founder' || id.startsWith('cat_');
        const hasChildren = (childrenOf[id] || []).length > 0;
        const isExpanded = expandedNodes.has(id);

        // Label: show expand indicator for hubs/categories
        let label = n.label || id;
        if (hasChildren && isHub) {
            label = isExpanded ? `▼ ${label}` : `▶ ${label}`;
        }

        const nodeObj = {
            id: id,
            label: label,
            color: { background: colors.bg, border: colors.border, highlight: { background: colors.bg, border: '#fff' }, hover: { background: colors.bg, border: '#fff' } },
            font: { color: colors.font, size: isHub ? 14 : 11, face: 'Inter, system-ui, sans-serif' },
            size: size,
            shape: isHub ? 'dot' : 'dot',
            borderWidth: isHub ? 3 : 1.5,
            _raw: n,
            _type: n.type,
        };

        // Fixed positions for hub nodes
        if (HUB_POSITIONS[id]) {
            nodeObj.x = HUB_POSITIONS[id].x;
            nodeObj.y = HUB_POSITIONS[id].y;
            nodeObj.fixed = { x: true, y: true };
            nodeObj.physics = false;
        }

        nodesArr.push(nodeObj);
    });

    // Build vis.js edge array
    const edgesArr = visibleEdges.map(e => {
        const isHierarchical = e.type === 'CONTAINS' || e.type === 'HAS_CATEGORY';
        return {
            from: e.source,
            to: e.target,
            label: isHierarchical ? '' : e.type.replace(/_/g, ' '),
            arrows: { to: { enabled: true, scaleFactor: 0.5 } },
            color: { color: isHierarchical ? '#2a2d3a' : '#4a4e69', opacity: isHierarchical ? 0.3 : 0.6, highlight: '#6c63ff', hover: '#6c63ff' },
            font: { color: '#6b7085', size: 9, strokeWidth: 2, strokeColor: '#0f1117', align: 'middle', background: 'rgba(15,17,23,0.7)' },
            smooth: { type: 'cubicBezier', roundness: 0.3 },
            width: isHierarchical ? 1 : 1.5,
            dashes: e.type === 'CONTRADICTS' ? [5, 5] : false,
            _edgeType: e.type,
        };
    });

    // Create or update vis DataSets
    if (!visNodes) {
        visNodes = new vis.DataSet(nodesArr);
        visEdges = new vis.DataSet(edgesArr);
    } else {
        visNodes.clear();
        visEdges.clear();
        visNodes.add(nodesArr);
        visEdges.add(edgesArr);
    }

    const container = document.getElementById('graph-container');

    const options = {
        physics: {
            enabled: true,
            solver: 'forceAtlas2Based',
            forceAtlas2Based: {
                gravitationalConstant: -60,
                centralGravity: 0.005,
                springLength: 150,
                springConstant: 0.04,
                damping: 0.5,
                avoidOverlap: 0.5,
            },
            stabilization: { iterations: 150, fit: true },
            maxVelocity: 25,
            minVelocity: 0.5,
        },
        interaction: {
            hover: true,
            tooltipDelay: 200,
            dragNodes: true,
            dragView: true,
            zoomView: true,
            navigationButtons: false,
            keyboard: { enabled: true },
        },
        nodes: {
            shape: 'dot',
            scaling: { min: 8, max: 45 },
        },
        edges: {
            smooth: { type: 'cubicBezier', roundness: 0.3 },
        },
        layout: {
            improvedLayout: true,
            randomSeed: 42,
        },
    };

    if (visNetwork) visNetwork.destroy();
    visNetwork = new vis.Network(container, { nodes: visNodes, edges: visEdges }, options);

    // ---- Click handler: expand/collapse or show detail ----
    visNetwork.on('click', (params) => {
        if (params.nodes.length === 0) {
            hideEditPanel();
            return;
        }
        const nodeId = params.nodes[0];
        const nodeData = allNodesById[nodeId];
        if (!nodeData) return;

        const isHub = nodeId === 'founder' || nodeId.startsWith('cat_');
        const hasChildren = (childrenOf[nodeId] || []).length > 0;

        if (isHub && hasChildren) {
            // Toggle expand/collapse
            if (expandedNodes.has(nodeId)) {
                expandedNodes.delete(nodeId);
                // Also collapse children of this node
                (childrenOf[nodeId] || []).forEach(childId => expandedNodes.delete(childId));
            } else {
                expandedNodes.add(nodeId);
            }
            buildVisGraph();
        } else {
            // Show edit panel + expand connections
            selectedNode = nodeId;
            if (!expandedNodes.has(nodeId)) {
                expandedNodes.add(nodeId);
                buildVisGraph();
            }
            showEditPanel(nodeData);
        }
    });

    // ---- Double-click to zoom ----
    visNetwork.on('doubleClick', (params) => {
        if (params.nodes.length > 0) {
            visNetwork.focus(params.nodes[0], { scale: 2.0, animation: { duration: 400 } });
        }
    });

    // ---- Hover highlights ----
    visNetwork.on('hoverNode', (params) => {
        const nodeId = params.node;
        const connected = visNetwork.getConnectedNodes(nodeId);
        const connectedEdges = visNetwork.getConnectedEdges(nodeId);

        // Dim non-connected nodes
        const updates = [];
        visNodes.forEach(n => {
            if (n.id !== nodeId && !connected.includes(n.id)) {
                updates.push({ id: n.id, opacity: 0.15 });
            }
        });
        visNodes.update(updates);

        // Highlight connected edges
        const edgeUpdates = [];
        visEdges.forEach(e => {
            if (connectedEdges.includes(e.id)) {
                edgeUpdates.push({ id: e.id, color: { color: '#6c63ff', opacity: 1 }, width: 2.5 });
            } else {
                edgeUpdates.push({ id: e.id, color: { ...e.color, opacity: 0.08 } });
            }
        });
        visEdges.update(edgeUpdates);
    });

    visNetwork.on('blurNode', () => {
        // Reset all opacities
        const nodeUpdates = [];
        visNodes.forEach(n => { nodeUpdates.push({ id: n.id, opacity: 1.0 }); });
        visNodes.update(nodeUpdates);

        const edgeUpdates = [];
        visEdges.forEach(e => {
            const isH = e._edgeType === 'CONTAINS' || e._edgeType === 'HAS_CATEGORY';
            edgeUpdates.push({ id: e.id, color: { color: isH ? '#2a2d3a' : '#4a4e69', opacity: isH ? 0.3 : 0.6 }, width: isH ? 1 : 1.5 });
        });
        visEdges.update(edgeUpdates);
    });

    // Fit to view
    setTimeout(() => { if (visNetwork) visNetwork.fit({ animation: { duration: 500 } }); }, 300);
}

// =========================================================================
// Filter
// =========================================================================
function filterGraph(type, btn) {
    graphFilter = type;
    document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
    if (btn) btn.classList.add('active');
    buildVisGraph();
}

// =========================================================================
// Node List Panel
// =========================================================================
function renderNodeList() {
    const list = document.getElementById('node-list');
    const nodes = graphData.nodes || [];
    if (nodes.length === 0) {
        list.innerHTML = '<li class="muted">No nodes yet. Run ingestion first.</li>';
        return;
    }

    // Group by type, skip founder/category
    const displayNodes = nodes.filter(n => n.type !== 'founder' && n.type !== 'category');
    list.innerHTML = displayNodes.map(n => `
        <li onclick="selectNodeFromList('${esc(n.id)}')" style="cursor:pointer;">
            <span class="node-type-badge ${n.type}">${n.type.replace(/_/g, ' ')}</span>
            <span>${esc(n.label)}</span>
        </li>
    `).join('');
}

function filterNodeList() {
    const q = document.getElementById('node-search').value.toLowerCase();
    document.querySelectorAll('#node-list li').forEach(li => {
        li.style.display = li.textContent.toLowerCase().includes(q) ? '' : 'none';
    });
}

function selectNodeFromList(nodeId) {
    const node = allNodesById[nodeId];
    if (!node) return;
    selectedNode = nodeId;

    // Ensure the node is visible by expanding its parent
    const parentCat = allEdges.find(e => e.target === nodeId && e.type === 'CONTAINS');
    if (parentCat) {
        expandedNodes.add('founder');
        expandedNodes.add(parentCat.source);
    }
    expandedNodes.add(nodeId);
    buildVisGraph();

    showEditPanel(node);

    // Focus on node in graph
    setTimeout(() => {
        if (visNetwork) {
            visNetwork.selectNodes([nodeId]);
            visNetwork.focus(nodeId, { scale: 1.5, animation: { duration: 400 } });
        }
    }, 400);
}

// =========================================================================
// Edit Panel
// =========================================================================
function showEditPanel(node) {
    const el = document.getElementById('node-detail');
    const type = node.type || 'unknown';
    const colors = NODE_COLORS[type] || NODE_COLORS.unknown;

    let fieldsHtml = `
        <div class="detail-header">
            <span class="node-type-badge ${type}" style="background:${colors.bg}; color:${colors.font}">${type.replace(/_/g, ' ')}</span>
            <strong>${esc(node.label)}</strong>
        </div>
        <div class="detail-fields">
            <div class="detail-field">
                <span class="field-label">ID</span>
                <span class="field-value">${esc(node.id)}</span>
            </div>
    `;

    // Type-specific editable fields
    if (type === 'belief') {
        fieldsHtml += editField('topic', 'Topic', node.topic || '', 'text');
        fieldsHtml += editField('stance', 'Stance', node.stance || '', 'textarea');
        fieldsHtml += editField('confidence', 'Confidence', node.confidence || 0.5, 'number', '0', '1', '0.05');
        fieldsHtml += editField('opposes', 'Opposes', node.opposes || '', 'textarea');
    } else if (type === 'story') {
        fieldsHtml += editField('title', 'Title', node.title || '', 'text');
        fieldsHtml += editField('summary', 'Summary', node.summary || '', 'textarea');
        fieldsHtml += editField('emotional_register', 'Register', node.emotional_register || '', 'select',
            null, null, null, ['controlled_anger', 'quiet_authority', 'earned_vulnerability', 'generosity', 'paranoid_optimist']);
        fieldsHtml += editField('contrast_pair', 'Contrast Pair', node.contrast_pair || '', 'text');
        fieldsHtml += editField('virality_potential', 'Virality', node.virality_potential || 'medium', 'select',
            null, null, null, ['low', 'medium', 'high']);
    } else if (type === 'style_rule') {
        fieldsHtml += editField('rule_type', 'Rule Type', node.rule_type || '', 'select',
            null, null, null, ['opening', 'closing', 'rhythm', 'rhetorical_move', 'vocabulary', 'punctuation']);
        fieldsHtml += editField('description', 'Description', node.description || '', 'textarea');
        fieldsHtml += editField('anti_pattern', 'Anti-Pattern', node.anti_pattern || '', 'textarea');
        fieldsHtml += editField('platform', 'Platform', node.platform || 'universal', 'select',
            null, null, null, ['universal', 'linkedin', 'twitter', 'email']);
    } else if (type === 'thinking_model') {
        fieldsHtml += editField('name', 'Name', node.name || '', 'text');
        fieldsHtml += editField('description', 'Description', node.description || '', 'textarea');
        fieldsHtml += editField('priority', 'Priority', node.priority || 0, 'number', '0', '10', '1');
    } else if (type === 'contrast_pair') {
        fieldsHtml += editField('left', 'Left Side', node.left || '', 'text');
        fieldsHtml += editField('right', 'Right Side', node.right || '', 'text');
        fieldsHtml += editField('description', 'Description', node.description || '', 'textarea');
    }

    // Connections summary
    const outgoing = allEdges.filter(e => e.source === node.id && e.type !== 'CONTAINS' && e.type !== 'HAS_CATEGORY');
    const incoming = allEdges.filter(e => e.target === node.id && e.type !== 'CONTAINS' && e.type !== 'HAS_CATEGORY');

    if (outgoing.length > 0 || incoming.length > 0) {
        fieldsHtml += `<div class="connections-section">
            <span class="field-label">Connections</span>
            <div class="connection-list">`;
        outgoing.forEach(e => {
            const target = allNodesById[e.target];
            fieldsHtml += `<div class="connection-item out" onclick="selectNodeFromList('${esc(e.target)}')">
                <span class="edge-type">${e.type.replace(/_/g, ' ')}</span> → ${esc(target?.label || e.target)}
            </div>`;
        });
        incoming.forEach(e => {
            const source = allNodesById[e.source];
            fieldsHtml += `<div class="connection-item in" onclick="selectNodeFromList('${esc(e.source)}')">
                ${esc(source?.label || e.source)} → <span class="edge-type">${e.type.replace(/_/g, ' ')}</span>
            </div>`;
        });
        fieldsHtml += `</div></div>`;
    }

    fieldsHtml += '</div>';

    // Action buttons (don't show for founder/category)
    const isEditable = type !== 'founder' && type !== 'category';
    if (isEditable) {
        fieldsHtml += `
            <div class="edit-actions">
                <button class="btn btn-primary" onclick="saveNodeEdit('${esc(node.id)}')">Save Changes</button>
                <button class="btn btn-danger" onclick="deleteNode('${esc(node.id)}')">Delete Node</button>
            </div>`;
    }

    el.innerHTML = fieldsHtml;
    el.style.display = 'block';
}

function editField(name, label, value, type, min, max, step, options) {
    let input;
    if (type === 'textarea') {
        input = `<textarea class="edit-input" data-field="${name}" rows="3">${esc(String(value))}</textarea>`;
    } else if (type === 'select') {
        const opts = (options || []).map(o =>
            `<option value="${o}" ${o === value ? 'selected' : ''}>${o.replace(/_/g, ' ')}</option>`
        ).join('');
        input = `<select class="edit-input" data-field="${name}">${opts}</select>`;
    } else if (type === 'number') {
        input = `<input class="edit-input" data-field="${name}" type="number" value="${value}" min="${min || ''}" max="${max || ''}" step="${step || '1'}">`;
    } else {
        input = `<input class="edit-input" data-field="${name}" type="text" value="${esc(String(value))}">`;
    }
    return `<div class="detail-field"><span class="field-label">${label}</span>${input}</div>`;
}

function hideEditPanel() {
    const el = document.getElementById('node-detail');
    el.innerHTML = '<p class="muted">Click a node to view & edit details</p>';
}

async function saveNodeEdit(nodeId) {
    const fields = document.querySelectorAll('#node-detail .edit-input');
    const props = {};
    fields.forEach(f => {
        const key = f.dataset.field;
        let val = f.value;
        if (f.type === 'number') val = parseFloat(val);
        props[key] = val;
    });

    try {
        const res = await fetch(`${API}/api/graph/nodes/${encodeURIComponent(nodeId)}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ properties: props }),
        });
        const data = await res.json();
        if (data.status === 'ok') {
            showToast('Node saved');
            // Reload graph to reflect changes
            await loadGraph();
        } else {
            showToast('Save failed: ' + (data.detail || ''), 'error');
        }
    } catch (e) {
        showToast('Save failed: ' + e.message, 'error');
    }
}

async function deleteNode(nodeId) {
    if (!confirm(`Delete node "${nodeId}"? This cannot be undone.`)) return;
    try {
        const res = await fetch(`${API}/api/graph/nodes/${encodeURIComponent(nodeId)}`, { method: 'DELETE' });
        const data = await res.json();
        if (data.status === 'ok') {
            showToast('Node deleted');
            expandedNodes.delete(nodeId);
            await loadGraph();
        } else {
            showToast('Delete failed: ' + (data.detail || ''), 'error');
        }
    } catch (e) {
        showToast('Delete failed: ' + e.message, 'error');
    }
}

function showAddNodeModal() {
    const modal = document.getElementById('add-node-modal');
    modal.style.display = 'flex';
}

function closeAddNodeModal() {
    document.getElementById('add-node-modal').style.display = 'none';
}

async function addNode() {
    const type = document.getElementById('new-node-type').value;
    const idInput = document.getElementById('new-node-id').value.trim();
    const labelInput = document.getElementById('new-node-label').value.trim();
    if (!idInput || !labelInput) return showToast('ID and Label are required', 'error');

    const fullId = `${type}_${idInput.replace(/\s+/g, '_').toLowerCase()}`;
    const props = { label: labelInput };

    // Type-specific defaults
    if (type === 'belief') { props.topic = 'general'; props.stance = ''; props.confidence = 0.5; }
    else if (type === 'story') { props.title = labelInput; props.summary = ''; props.emotional_register = 'quiet_authority'; }
    else if (type === 'style_rule') { props.rule_type = 'opening'; props.description = ''; }
    else if (type === 'thinking_model') { props.name = labelInput; props.description = ''; props.priority = 5; }

    try {
        const res = await fetch(`${API}/api/graph/nodes`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ id: fullId, node_type: type, properties: props }),
        });
        const data = await res.json();
        if (data.status === 'ok') {
            showToast('Node created');
            closeAddNodeModal();
            await loadGraph();
        } else {
            showToast('Create failed: ' + (data.detail || ''), 'error');
        }
    } catch (e) {
        showToast('Create failed: ' + e.message, 'error');
    }
}

// =========================================================================
// History
// =========================================================================
async function loadHistory() {
    const container = document.getElementById('history-list');
    try {
        const res = await fetch(`${API}/api/outputs`);
        const data = await res.json();
        if (!data.outputs || data.outputs.length === 0) {
            container.innerHTML = '<p class="muted">No generated posts yet.</p>';
            return;
        }
        container.innerHTML = data.outputs.map(o => `
            <div class="history-item">
                <div class="meta">${esc(o.name)} (${o.size} bytes)</div>
                <div class="content">${esc(o.content)}</div>
            </div>
        `).join('');
    } catch (e) { container.innerHTML = `<p class="text-red">Failed: ${esc(e.message)}</p>`; }
}

// =========================================================================
// Config
// =========================================================================
async function loadConfig() {
    try {
        const res = await fetch(`${API}/api/config`);
        const data = await res.json();
        document.getElementById('cfg-provider').value = data.llm?.provider || 'ollama';
        document.getElementById('cfg-model').value = data.llm?.model || '';
        document.getElementById('cfg-url').value = data.llm?.base_url || '';
    } catch (e) { console.error('Failed to load config:', e); }
}

async function saveConfig() {
    const status = document.getElementById('config-status');
    try {
        const payload = {
            provider: document.getElementById('cfg-provider').value,
            model: document.getElementById('cfg-model').value,
            base_url: document.getElementById('cfg-url').value,
        };
        const apiKey = document.getElementById('cfg-apikey').value.trim();
        if (apiKey) payload.api_key = apiKey;
        const res = await fetch(`${API}/api/config`, {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        await res.json();
        status.innerHTML = '<span class="status ok">Configuration saved</span>';
    } catch (e) { status.innerHTML = `<span class="status error">Failed: ${esc(e.message)}</span>`; }
}

// =========================================================================
// Utilities
// =========================================================================
function esc(str) {
    if (str == null) return '';
    const div = document.createElement('div');
    div.textContent = String(str);
    return div.innerHTML;
}

function showToast(msg, type = 'ok') {
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = msg;
    document.body.appendChild(toast);
    setTimeout(() => { toast.classList.add('show'); }, 10);
    setTimeout(() => { toast.classList.remove('show'); setTimeout(() => toast.remove(), 300); }, 2500);
}

// =========================================================================
// Founders
// =========================================================================
async function loadFounders() {
    try {
        const res = await fetch(`${API}/api/founders`);
        const data = await res.json();
        const sel = document.getElementById('founder-selector');
        sel.innerHTML = '';
        (data.founders || []).forEach(f => {
            const opt = document.createElement('option');
            opt.value = f.slug;
            opt.textContent = f.display_name + (f.has_graph ? '' : ' (no graph)');
            if (f.active) opt.selected = true;
            sel.appendChild(opt);
        });
    } catch (e) { console.error('Failed to load founders:', e); }
}

async function switchFounder(slug) {
    try {
        await fetch(`${API}/api/founders/active`, {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ slug }),
        });
        showToast(`Switched to ${slug}`);
        loadStats();
        loadPersonalityCard();
    } catch (e) { showToast('Switch failed', 'error'); }
}

// =========================================================================
// Creativity Slider
// =========================================================================
function updateCreativityLabel(val) {
    const el = document.getElementById('creativity-value');
    if (val <= 30) el.textContent = `${val}% — Follow Proven Patterns`;
    else if (val <= 70) el.textContent = `${val}% — Balanced`;
    else el.textContent = `${val}% — Creative Freedom`;
}

// =========================================================================
// Coverage
// =========================================================================
async function loadCoverage() {
    const sel = document.getElementById('founder-selector');
    const slug = sel ? sel.value : 'sharath';
    try {
        const res = await fetch(`${API}/api/coverage/${slug}`);
        const data = await res.json();
        renderCoverage(data);
    } catch (e) {
        console.error('Failed to load coverage:', e);
        document.getElementById('coverage-overview').innerHTML = '<p class="muted">No coverage data yet. Generate some posts first.</p>';
    }
}

function renderCoverage(data) {
    // Overall bar
    const fill = document.getElementById('coverage-fill');
    const pct = document.getElementById('coverage-pct');
    if (fill) fill.style.width = `${data.overall_pct || 0}%`;
    if (pct) pct.textContent = `${data.overall_pct || 0}% (${data.covered_nodes || 0}/${data.total_nodes || 0})`;

    // By type breakdown
    const byType = document.getElementById('coverage-by-type');
    const types = data.by_type || {};
    byType.innerHTML = Object.entries(types).map(([type, info]) => `
        <div class="coverage-type-row">
            <span class="coverage-type-label">${type.replace(/_/g, ' ')}</span>
            <div class="coverage-bar"><div class="coverage-bar-fill" style="width:${info.pct}%"></div></div>
            <span class="coverage-type-pct">${info.covered}/${info.total} (${info.pct}%)</span>
        </div>
    `).join('');

    // Heatmap
    const heatmap = document.getElementById('coverage-heatmap');
    const heatmapData = data.heatmap || {};
    const allNodes = [...Object.entries(heatmapData)];

    // Also show unused nodes in heatmap
    const opportunities = data.opportunities || [];
    opportunities.forEach(o => {
        if (!heatmapData[o.node_id]) {
            allNodes.push([o.node_id, 0]);
        }
    });

    heatmap.innerHTML = allNodes.slice(0, 200).map(([nid, count]) => {
        const intensity = count === 0 ? 0 : Math.min(1, count / 5);
        const bg = count === 0
            ? 'rgba(107, 112, 133, 0.2)'
            : `rgba(52, 211, 153, ${0.2 + intensity * 0.6})`;
        return `<div class="heatmap-cell" style="background:${bg}" title="${nid}: used ${count}x">${count}</div>`;
    }).join('');

    // Opportunities
    const opps = document.getElementById('coverage-opportunities');
    if (opportunities.length === 0) {
        opps.innerHTML = '<p class="muted">All nodes have been covered!</p>';
    } else {
        opps.innerHTML = opportunities.slice(0, 30).map(o => `
            <div class="opportunity-item">
                <span class="node-type-badge ${o.node_type}">${o.node_type.replace(/_/g, ' ')}</span>
                <span>${esc(o.label)}</span>
            </div>
        `).join('');
    }
}

// =========================================================================
// Init
// =========================================================================
document.addEventListener('DOMContentLoaded', () => {
    loadFounders();
    loadStats();
    loadPersonalityCard();
});
