
function setActiveNav(pageName){
  document.querySelectorAll('.nav-tab').forEach(tab=>{
    tab.classList.toggle('active', tab.dataset.page===pageName);
  });
}
function updateTopicLabel(topic){
  const target=document.getElementById('summaryTopic');
  if(target) target.textContent=topic || 'Machine Learning';
}
function bindSharedControls(defaultTopic='Machine Learning'){
  setActiveNav(document.body.dataset.page || 'overview');
  const searchInput=document.getElementById('searchInput');
  const domainSelect=document.getElementById('domainSelect');
  const searchBtn=document.getElementById('searchBtn');
  if(searchInput) searchInput.value=defaultTopic;
  if(searchBtn){
    searchBtn.addEventListener('click',()=>{
      const value=(searchInput?.value || '').trim();
      const status=document.getElementById('statusBar');
      if(value){
        updateTopicLabel(value);
        if(status) status.textContent=`Prototype search triggered for "${value}". Front-end is ready and can later call the real back-end.`;
      }
    });
  }
  if(domainSelect){
    domainSelect.addEventListener('change',()=>{
      const status=document.getElementById('statusBar');
      if(status) status.textContent=`Domain changed to "${domainSelect.value}". This selector is already wired in the front-end.`;
    });
  }
}
