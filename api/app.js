async function loadArticles() {
  try {
    const response = await fetch('/api/articles');
    
    if (!response.ok) {
      throw new Error('Network response was not ok');
    }
    
    const articles = await response.json();
    console.log("Articles loaded:", articles);
    
  } catch (error) {
    console.error('Could not reach the article database:', error);
  }
}

loadArticles();
