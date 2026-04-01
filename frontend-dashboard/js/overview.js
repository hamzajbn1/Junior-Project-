
let mainChart;
let citationChart;

function withTimeout(promise, ms=4000){
  let timer;
  const timeoutPromise = new Promise((_, reject)=>{
    timer = setTimeout(()=>reject(new Error('Data loading timed out.')), ms);
  });
  return Promise.race([promise.finally(()=>clearTimeout(timer)), timeoutPromise]);
}

function getOverviewData(){
  // Replace this later with a real fetch('/api/overview?...')
  return withTimeout(new Promise(resolve=>{
    setTimeout(()=>resolve(window.OVERVIEW_MOCK_DATA), 450);
  }), 4000);
}

function formatNumber(value){
  return new Intl.NumberFormat().format(value);
}

function renderSummary(summary){
  document.getElementById('summaryTopic').textContent = summary.selected_topic;
  document.getElementById('summaryPeriod').textContent = `${summary.from_year} - ${summary.to_year}`;
  document.getElementById('summaryPubs').textContent = formatNumber(summary.total_publications);
  document.getElementById('summaryCitations').textContent = formatNumber(summary.total_citations);
  document.getElementById('summaryAvg').textContent = summary.avg_citations_per_paper.toFixed(1);
  document.getElementById('summaryH').textContent = summary.h_index;
  document.getElementById('summaryPublisher').textContent = summary.top_publisher;
  document.getElementById('summarySource').textContent = summary.data_source;
  const searchInput=document.getElementById('searchInput');
  if(searchInput) searchInput.value = summary.selected_topic;
}

function renderMainChart(rows){
  const years = rows.map(r=>r.year);
  const pubs = rows.map(r=>r.publications);
  const cites = rows.map(r=>r.citations);
  const ctx = document.getElementById('publicationsCitationsChart').getContext('2d');
  if(mainChart) mainChart.destroy();
  mainChart = new Chart(ctx, {
    data:{
      labels: years,
      datasets:[
        {type:'bar', label:'Publications', data:pubs, backgroundColor:'rgba(125,181,216,.78)', borderColor:'rgba(125,181,216,1)', borderWidth:1, yAxisID:'y'},
        {type:'line', label:'Citations', data:cites, borderColor:'#1f2937', backgroundColor:'#1f2937', borderWidth:2, pointRadius:4, tension:.25, yAxisID:'y1'}
      ]
    },
    options:{
      responsive:true,
      maintainAspectRatio:false,
      plugins:{legend:{position:'bottom'}},
      scales:{
        y:{beginAtZero:true, title:{display:true, text:'Publications'}},
        y1:{beginAtZero:true, position:'right', title:{display:true, text:'Citations'}, grid:{drawOnChartArea:false}},
        x:{title:{display:true, text:'Year'}}
      }
    }
  });
}

function renderCitationChart(rows){
  const years=rows.map(r=>r.year);
  const avg=rows.map(r=>r.avg_citations);
  const ctx=document.getElementById('citationTrendChart').getContext('2d');
  if(citationChart) citationChart.destroy();
  citationChart = new Chart(ctx,{
    type:'line',
    data:{
      labels:years,
      datasets:[{
        label:'Average Citations per Paper',
        data:avg,
        borderColor:'#2f6fa3',
        backgroundColor:'rgba(47,111,163,.18)',
        borderWidth:2,
        pointRadius:4,
        tension:.28,
        fill:true
      }]
    },
    options:{
      responsive:true,
      maintainAspectRatio:false,
      plugins:{legend:{position:'bottom'}},
      scales:{
        y:{beginAtZero:true,title:{display:true,text:'Average Citations'}},
        x:{title:{display:true,text:'Year'}}
      }
    }
  });
}

function renderList(id, rows, formatter){
  const el=document.getElementById(id);
  el.innerHTML=rows.map(formatter).join('');
}

function renderInsights(ins){
  document.getElementById('insightDirection').textContent=ins.trend_direction;
  document.getElementById('insightPeak').textContent=ins.peak_year;
  document.getElementById('insightTopic').textContent=ins.most_active_topic;
  document.getElementById('insightNote').textContent=ins.note;
}

async function initOverview(){
  bindSharedControls('Machine Learning');
  const loading=document.getElementById('loadingMessage');
  const error=document.getElementById('errorMessage');
  const status=document.getElementById('statusBar');
  loading.style.display='block';
  error.style.display='none';
  try{
    const data=await getOverviewData();
    renderSummary(data.summary);
    renderMainChart(data.publications_citations);
    renderCitationChart(data.citation_trend);
    renderList('topTopicsList', data.top_topics, row => `<div class="metric-item"><span class="metric-label">${row.name}</span><span class="metric-value">${row.papers} papers (${row.percentage}%)</span></div>`);
    renderList('topAuthorsList', data.top_authors, row => `<div class="metric-item"><span class="metric-label">${row.name}</span><span class="metric-value">${row.papers} pubs / ${row.citations} cites</span></div>`);
    renderList('topOrganizationsList', data.top_organizations, row => `<div class="metric-item"><span class="metric-label">${row.name}</span><span class="metric-value">${row.papers} pubs / ${row.citations} cites</span></div>`);
    renderInsights(data.trend_insights);
    status.textContent='Overview loaded successfully using mock data. Back-end can later replace this source with a real API response.';
  }catch(err){
    error.style.display='block';
    error.textContent=err.message || 'Failed to load overview data.';
    status.textContent='Overview failed to load. Loading/error handling is already prepared for API integration.';
  }finally{
    loading.style.display='none';
  }
}

document.addEventListener('DOMContentLoaded', initOverview);
