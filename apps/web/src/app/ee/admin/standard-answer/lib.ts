export interface StandardAnswerCategoryCreationRequest {
  name: string;
}

export interface StandardAnswerCreationRequest {
  keyword: string;
  answer: string;
  categories: number[];
  matchRegex: boolean;
  matchAnyKeywords: boolean;
}

const buildRequestBodyFromStandardAnswerCategoryCreationRequest = (
  request: StandardAnswerCategoryCreationRequest
) => {
  return JSON.stringify({
    name: request.name,
  });
};

const buildRequestBodyFromStandardAnswerCreationRequest = (
  request: StandardAnswerCreationRequest
) => {
  return JSON.stringify({
    keyword: request.keyword,
    answer: request.answer,
    categories: request.categories,
    match_regex: request.matchRegex,
    match_any_keywords: request.matchAnyKeywords,
  });
};
