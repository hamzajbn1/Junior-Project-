const OVERVIEW_MOCK_DATA = {
  summary: {
    selected_topic: "Machine Learning",
    from_year: 2015,
    to_year: 2025,
    total_publications: 1240,
    total_citations: 18650,
    avg_citations_per_paper: 15.0,
    h_index: 42,
    top_publisher: "NeurIPS",
    data_source: "CSKG + OpenAlex"
  },
  publications_citations: [
    { year: 2015, publications: 80, citations: 320 },
    { year: 2016, publications: 95, citations: 480 },
    { year: 2017, publications: 120, citations: 700 },
    { year: 2018, publications: 155, citations: 980 },
    { year: 2019, publications: 210, citations: 1420 },
    { year: 2020, publications: 265, citations: 2080 },
    { year: 2021, publications: 340, citations: 2950 },
    { year: 2022, publications: 320, citations: 3310 },
    { year: 2023, publications: 360, citations: 3820 },
    { year: 2024, publications: 390, citations: 4210 }
  ],
  citation_trend: [
    { year: 2015, avg_citations: 4.0 },
    { year: 2016, avg_citations: 5.1 },
    { year: 2017, avg_citations: 5.8 },
    { year: 2018, avg_citations: 6.3 },
    { year: 2019, avg_citations: 6.8 },
    { year: 2020, avg_citations: 7.9 },
    { year: 2021, avg_citations: 8.7 },
    { year: 2022, avg_citations: 9.1 },
    { year: 2023, avg_citations: 9.6 },
    { year: 2024, avg_citations: 10.2 }
  ],
  top_topics: [
    { name: "Deep Learning", papers: 320, percentage: 25.8 },
    { name: "Computer Vision", papers: 210, percentage: 16.9 },
    { name: "NLP", papers: 190, percentage: 15.3 },
    { name: "Reinforcement Learning", papers: 130, percentage: 10.5 },
    { name: "Graph Learning", papers: 110, percentage: 8.9 }
  ],
  top_authors: [
    { name: "Author A", papers: 18, citations: 520 },
    { name: "Author B", papers: 15, citations: 430 },
    { name: "Author C", papers: 13, citations: 410 },
    { name: "Author D", papers: 11, citations: 350 },
    { name: "Author E", papers: 10, citations: 315 }
  ],
  top_organizations: [
    { name: "MIT", papers: 70, citations: 2100 },
    { name: "Stanford", papers: 65, citations: 1980 },
    { name: "CMU", papers: 58, citations: 1720 },
    { name: "Oxford", papers: 46, citations: 1415 },
    { name: "Tsinghua", papers: 42, citations: 1290 }
  ],
  trend_insights: {
    trend_direction: "Increasing",
    peak_year: 2024,
    most_active_topic: "Deep Learning",
    note: "Research output and citations both show consistent growth over the displayed period."
  }
};

export default OVERVIEW_MOCK_DATA;
